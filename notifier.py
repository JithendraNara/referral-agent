import os
import smtplib
import logging
import httpx
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict
from config import GMAIL_USER, GMAIL_APP_PASSWORD, NOTIFICATION_EMAIL

logger = logging.getLogger(__name__)

# Optional webhook URLs from environment
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

def send_email_notification(new_jobs: List[Dict]):
    """
    Send an email notification with new job listings via Gmail SMTP.
    
    Args:
        new_jobs: List of job dictionaries with 'title', 'url', 'location' keys.
    """
    if not all([GMAIL_USER, GMAIL_APP_PASSWORD, NOTIFICATION_EMAIL]):
        logger.warning("Email credentials not configured. Skipping email notification.")
        _log_jobs_to_console(new_jobs)
        return False

    try:
        # Build email content
        subject = f"🚀 Referral Agent: Found {len(new_jobs)} New Job(s)!"
        body = _build_email_body(new_jobs)

        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = GMAIL_USER
        msg["To"] = NOTIFICATION_EMAIL

        # Attach HTML body
        msg.attach(MIMEText(body, "html"))

        # Send via Gmail SMTP
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, NOTIFICATION_EMAIL, msg.as_string())

        logger.info(f"✅ Email sent successfully to {NOTIFICATION_EMAIL}")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to send email: {e}")
        _log_jobs_to_console(new_jobs)
        return False


def _build_email_body(jobs: List[Dict]) -> str:
    """Build an HTML email body from job listings."""
    job_rows = ""
    for job in jobs:
        title = job.get("title", "Unknown Title")
        url = job.get("url", "#")
        location = job.get("location", "Unknown Location")
        company = job.get("company_name", "Unknown Company")
        
        job_rows += f"""
        <tr>
            <td style="padding: 10px; border-bottom: 1px solid #eee;">
                <strong>{company}</strong>
            </td>
            <td style="padding: 10px; border-bottom: 1px solid #eee;">
                <a href="{url}" style="color: #1a73e8; text-decoration: none;">{title}</a>
            </td>
            <td style="padding: 10px; border-bottom: 1px solid #eee;">
                {location}
            </td>
        </tr>
        """

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #333;">🎯 New Job Openings Found!</h2>
        <p>Your Referral Agent found the following new positions:</p>
        
        <table style="width: 100%; border-collapse: collapse; margin-top: 20px;">
            <thead>
                <tr style="background-color: #f5f5f5;">
                    <th style="padding: 10px; text-align: left;">Company</th>
                    <th style="padding: 10px; text-align: left;">Position</th>
                    <th style="padding: 10px; text-align: left;">Location</th>
                </tr>
            </thead>
            <tbody>
                {job_rows}
            </tbody>
        </table>
        
        <p style="margin-top: 20px; color: #666; font-size: 12px;">
            This is an automated message from your Referral Agent.
        </p>
    </body>
    </html>
    """
    return html


def _log_jobs_to_console(jobs: List[Dict]):
    """Fallback: Log jobs to console when email is not configured."""
    logger.info("📧 EMAIL NOTIFICATION (Console Fallback):")
    logger.info(f"   Found {len(jobs)} new job(s):")
    for job in jobs:
        logger.info(f"   - {job.get('title')} @ {job.get('location')} ({job.get('url')})")


def send_slack_notification(new_jobs: List[Dict]) -> bool:
    """
    Send a Slack notification via webhook.
    
    Args:
        new_jobs: List of job dictionaries.
    
    Returns:
        True if successful, False otherwise.
    """
    if not SLACK_WEBHOOK_URL:
        logger.debug("Slack webhook not configured, skipping.")
        return False
    
    try:
        # Build Slack blocks for rich formatting
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🚀 {len(new_jobs)} New Job(s) Found!",
                    "emoji": True
                }
            },
            {"type": "divider"}
        ]
        
        for job in new_jobs[:10]:  # Limit to 10 jobs per message
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*<{job.get('url')}|{job.get('title')}>*\n"
                        f"🏢 {job.get('company_name', 'Unknown')} • 📍 {job.get('location', 'Not specified')}"
                    )
                }
            })
        
        if len(new_jobs) > 10:
            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"_...and {len(new_jobs) - 10} more_"}]
            })
        
        payload = {"blocks": blocks}
        
        with httpx.Client() as client:
            response = client.post(SLACK_WEBHOOK_URL, json=payload)
            response.raise_for_status()
        
        logger.info("✅ Slack notification sent successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to send Slack notification: {e}")
        return False


def send_discord_notification(new_jobs: List[Dict]) -> bool:
    """
    Send a Discord notification via webhook.
    
    Args:
        new_jobs: List of job dictionaries.
    
    Returns:
        True if successful, False otherwise.
    """
    if not DISCORD_WEBHOOK_URL:
        logger.debug("Discord webhook not configured, skipping.")
        return False
    
    try:
        # Build Discord embed
        embeds = [{
            "title": f"🚀 {len(new_jobs)} New Job(s) Found!",
            "color": 0x00ff00,  # Green
            "fields": []
        }]
        
        for job in new_jobs[:10]:  # Limit to 10 jobs
            embeds[0]["fields"].append({
                "name": job.get('title', 'Unknown Title'),
                "value": f"🏢 {job.get('company_name', 'Unknown')}\n📍 {job.get('location', 'N/A')}\n[Apply]({job.get('url')})",
                "inline": True
            })
        
        payload = {"embeds": embeds}
        
        with httpx.Client() as client:
            response = client.post(DISCORD_WEBHOOK_URL, json=payload)
            response.raise_for_status()
        
        logger.info("✅ Discord notification sent successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to send Discord notification: {e}")
        return False


def send_all_notifications(new_jobs: List[Dict]):
    """
    Send notifications through all configured channels.
    
    Args:
        new_jobs: List of job dictionaries.
    """
    results = {
        "email": send_email_notification(new_jobs),
        "slack": send_slack_notification(new_jobs),
        "discord": send_discord_notification(new_jobs)
    }
    
    successful = [k for k, v in results.items() if v]
    if successful:
        logger.info(f"Notifications sent via: {', '.join(successful)}")
    else:
        logger.warning("No notifications were sent successfully")
