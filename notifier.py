"""
Notification system with multiple channels.
Supports email, Slack, Discord with proper formatting.
"""
import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
import httpx

from config import settings

logger = logging.getLogger(__name__)


class NotificationError(Exception):
    """Custom exception for notification failures."""
    pass


@dataclass
class NotificationResult:
    """Result of a notification attempt."""
    channel: str
    success: bool
    message: str = ""
    error: Optional[str] = None


class NotificationChannel(ABC):
    """Abstract base class for notification channels."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Channel name for logging."""
        pass
    
    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Check if channel is properly configured."""
        pass
    
    @abstractmethod
    def send(self, jobs: List[Dict]) -> NotificationResult:
        """Send notification with job listings."""
        pass


class EmailChannel(NotificationChannel):
    """Email notification via Gmail SMTP."""
    
    def __init__(self):
        self.smtp_host = "smtp.gmail.com"
        self.smtp_port = 465
        self.sender = settings.GMAIL_USER
        self.password = settings.GMAIL_APP_PASSWORD
        self.recipient = settings.NOTIFICATION_EMAIL
    
    @property
    def name(self) -> str:
        return "email"
    
    @property
    def is_configured(self) -> bool:
        return all([self.sender, self.password, self.recipient])
    
    def send(self, jobs: List[Dict]) -> NotificationResult:
        if not self.is_configured:
            return NotificationResult(
                channel=self.name,
                success=False,
                error="Email credentials not configured"
            )
        
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"🚀 Referral Agent: {len(jobs)} New Job(s) Found!"
            msg["From"] = self.sender
            msg["To"] = self.recipient
            
            html_body = self._build_html_body(jobs)
            msg.attach(MIMEText(html_body, "html"))
            
            with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port) as server:
                server.login(self.sender, self.password)
                server.sendmail(self.sender, self.recipient, msg.as_string())
            
            logger.info(f"✅ Email sent to {self.recipient}")
            return NotificationResult(
                channel=self.name,
                success=True,
                message=f"Sent to {self.recipient}"
            )
            
        except Exception as e:
            logger.error(f"❌ Email failed: {e}")
            return NotificationResult(
                channel=self.name,
                success=False,
                error=str(e)
            )
    
    def _build_html_body(self, jobs: List[Dict]) -> str:
        """Build professional HTML email."""
        job_rows = ""
        for job in jobs:
            job_rows += f"""
            <tr>
                <td style="padding: 12px 16px; border-bottom: 1px solid #eee;">
                    <strong style="color: #333;">{job.get('company_name', 'N/A')}</strong>
                </td>
                <td style="padding: 12px 16px; border-bottom: 1px solid #eee;">
                    <a href="{job.get('url', '#')}" style="color: #2563eb; text-decoration: none; font-weight: 500;">
                        {job.get('title', 'Unknown Title')}
                    </a>
                </td>
                <td style="padding: 12px 16px; border-bottom: 1px solid #eee; color: #666;">
                    📍 {job.get('location', 'Not specified')}
                </td>
                <td style="padding: 12px 16px; border-bottom: 1px solid #eee; color: #888; font-size: 13px;">
                    {job.get('posted_date', 'N/A')}
                </td>
            </tr>
            """
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; margin: 0; padding: 20px;">
            <div style="max-width: 700px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
                <div style="background: linear-gradient(135deg, #3b82f6, #8b5cf6); padding: 24px 32px; color: white;">
                    <h1 style="margin: 0; font-size: 22px; font-weight: 600;">🎯 New Job Openings Found!</h1>
                    <p style="margin: 8px 0 0; opacity: 0.9; font-size: 14px;">Your Referral Agent found {len(jobs)} new position(s)</p>
                </div>
                
                <div style="padding: 24px 32px;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <thead>
                            <tr style="background: #f8f9fa;">
                                <th style="padding: 12px 16px; text-align: left; font-size: 12px; text-transform: uppercase; color: #666; font-weight: 600;">Company</th>
                                <th style="padding: 12px 16px; text-align: left; font-size: 12px; text-transform: uppercase; color: #666; font-weight: 600;">Position</th>
                                <th style="padding: 12px 16px; text-align: left; font-size: 12px; text-transform: uppercase; color: #666; font-weight: 600;">Location</th>
                                <th style="padding: 12px 16px; text-align: left; font-size: 12px; text-transform: uppercase; color: #666; font-weight: 600;">Posted</th>
                            </tr>
                        </thead>
                        <tbody>
                            {job_rows}
                        </tbody>
                    </table>
                </div>
                
                <div style="padding: 20px 32px; background: #f8f9fa; text-align: center; font-size: 13px; color: #888;">
                    <p style="margin: 0;">Sent by <strong>Referral Agent</strong> • <a href="#" style="color: #3b82f6;">Dashboard</a></p>
                </div>
            </div>
        </body>
        </html>
        """


class SlackChannel(NotificationChannel):
    """Slack notification via webhook."""
    
    def __init__(self):
        self.webhook_url = settings.SLACK_WEBHOOK_URL
    
    @property
    def name(self) -> str:
        return "slack"
    
    @property
    def is_configured(self) -> bool:
        return bool(self.webhook_url)
    
    def send(self, jobs: List[Dict]) -> NotificationResult:
        if not self.is_configured:
            return NotificationResult(
                channel=self.name,
                success=False,
                error="Slack webhook not configured"
            )
        
        try:
            blocks = self._build_blocks(jobs)
            
            with httpx.Client(timeout=30) as client:
                response = client.post(self.webhook_url, json={"blocks": blocks})
                response.raise_for_status()
            
            logger.info("✅ Slack notification sent")
            return NotificationResult(channel=self.name, success=True)
            
        except Exception as e:
            logger.error(f"❌ Slack failed: {e}")
            return NotificationResult(channel=self.name, success=False, error=str(e))
    
    def _build_blocks(self, jobs: List[Dict]) -> List[Dict]:
        """Build Slack Block Kit message."""
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"🚀 {len(jobs)} New Job(s) Found!", "emoji": True}
            },
            {"type": "divider"}
        ]
        
        for job in jobs[:10]:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*<{job.get('url', '#')}|{job.get('title', 'Unknown')}>*\n"
                        f"🏢 {job.get('company_name', 'N/A')} • 📍 {job.get('location', 'N/A')}"
                    )
                }
            })
        
        if len(jobs) > 10:
            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"_...and {len(jobs) - 10} more jobs_"}]
            })
        
        return blocks


class DiscordChannel(NotificationChannel):
    """Discord notification via webhook."""
    
    def __init__(self):
        self.webhook_url = settings.DISCORD_WEBHOOK_URL
    
    @property
    def name(self) -> str:
        return "discord"
    
    @property
    def is_configured(self) -> bool:
        return bool(self.webhook_url)
    
    def send(self, jobs: List[Dict]) -> NotificationResult:
        if not self.is_configured:
            return NotificationResult(
                channel=self.name,
                success=False,
                error="Discord webhook not configured"
            )
        
        try:
            embed = self._build_embed(jobs)
            
            with httpx.Client(timeout=30) as client:
                response = client.post(self.webhook_url, json={"embeds": [embed]})
                response.raise_for_status()
            
            logger.info("✅ Discord notification sent")
            return NotificationResult(channel=self.name, success=True)
            
        except Exception as e:
            logger.error(f"❌ Discord failed: {e}")
            return NotificationResult(channel=self.name, success=False, error=str(e))
    
    def _build_embed(self, jobs: List[Dict]) -> Dict:
        """Build Discord embed message."""
        fields = []
        for job in jobs[:10]:
            fields.append({
                "name": job.get('title', 'Unknown'),
                "value": f"🏢 {job.get('company_name', 'N/A')}\n📍 {job.get('location', 'N/A')}\n[Apply]({job.get('url', '#')})",
                "inline": True
            })
        
        return {
            "title": f"🚀 {len(jobs)} New Job(s) Found!",
            "color": 0x3b82f6,
            "fields": fields,
            "footer": {"text": "Referral Agent"}
        }


class NotificationService:
    """
    Manages multiple notification channels.
    Handles parallel sending and aggregates results.
    """
    
    def __init__(self):
        self.channels: List[NotificationChannel] = [
            EmailChannel(),
            SlackChannel(),
            DiscordChannel(),
        ]
    
    def get_configured_channels(self) -> List[str]:
        """Get list of configured channel names."""
        return [ch.name for ch in self.channels if ch.is_configured]
    
    def send_all(
        self,
        jobs: List[Dict],
        channels: List[str] = None
    ) -> Dict[str, NotificationResult]:
        """
        Send notifications through all configured channels.
        
        Args:
            jobs: List of job dictionaries
            channels: Optional list of specific channels to use
        
        Returns:
            Dict mapping channel names to their results
        """
        if not jobs:
            logger.info("No jobs to notify about")
            return {}
        
        results = {}
        
        # Filter channels if specified
        active_channels = self.channels
        if channels:
            active_channels = [ch for ch in self.channels if ch.name in channels]
        
        # Filter to only configured channels
        active_channels = [ch for ch in active_channels if ch.is_configured]
        
        if not active_channels:
            logger.warning("No notification channels configured")
            self._log_to_console(jobs)
            return {}
        
        # Send to all channels in parallel
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(ch.send, jobs): ch.name
                for ch in active_channels
            }
            
            for future in as_completed(futures):
                channel_name = futures[future]
                try:
                    result = future.result()
                    results[channel_name] = result
                except Exception as e:
                    results[channel_name] = NotificationResult(
                        channel=channel_name,
                        success=False,
                        error=str(e)
                    )
        
        # Log summary
        successful = [k for k, v in results.items() if v.success]
        if successful:
            logger.info(f"📨 Notifications sent via: {', '.join(successful)}")
        else:
            logger.warning("⚠️ No notifications were sent successfully")
        
        return results
    
    def _log_to_console(self, jobs: List[Dict]):
        """Fallback: Log jobs to console."""
        logger.info("📧 NOTIFICATION (Console Fallback):")
        logger.info(f"   Found {len(jobs)} new job(s):")
        for job in jobs:
            logger.info(f"   - {job.get('title')} @ {job.get('company_name')} ({job.get('url')})")


# Singleton instance
notification_service = NotificationService()


# Legacy function for backward compatibility
def send_all_notifications(new_jobs: List[Dict]) -> Dict[str, NotificationResult]:
    """Legacy wrapper for notification_service.send_all()."""
    return notification_service.send_all(new_jobs)


def send_email_notification(new_jobs: List[Dict]) -> bool:
    """Legacy wrapper for email-only notification."""
    channel = EmailChannel()
    if not channel.is_configured:
        return False
    result = channel.send(new_jobs)
    return result.success


def send_slack_notification(new_jobs: List[Dict]) -> bool:
    """Legacy wrapper for Slack-only notification."""
    channel = SlackChannel()
    if not channel.is_configured:
        return False
    result = channel.send(new_jobs)
    return result.success


def send_discord_notification(new_jobs: List[Dict]) -> bool:
    """Legacy wrapper for Discord-only notification."""
    channel = DiscordChannel()
    if not channel.is_configured:
        return False
    result = channel.send(new_jobs)
    return result.success
