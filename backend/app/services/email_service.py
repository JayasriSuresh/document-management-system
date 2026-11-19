"""
Email delivery service for DMS identity workflows.

Supports SMTP in production with TLS/SSL, and formatted console logging in development/test.
Never exposes sensitive tokens in production logs or unsecured channels.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from app.config import settings

logger = logging.getLogger("dms.email")


class EmailService:
    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USERNAME or settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD or settings.SMTP_PASS
        self.from_email = settings.SMTP_FROM_EMAIL or self.smtp_user or "security@dms.local"
        self.from_name = settings.SMTP_FROM_NAME
        self.use_tls = settings.SMTP_USE_TLS
        self.use_ssl = settings.SMTP_USE_SSL
        self.frontend_url = settings.FRONTEND_URL.rstrip("/")

    def send_email(self, to_email: str, subject: str, html_content: str, text_content: str) -> bool:
        """
        Send an email via SMTP or log to console in development.
        Returns True if successful, raises Exception if critical in production.
        """
        if not self.smtp_host:
            if settings.is_production:
                logger.error("SMTP_HOST not configured in production. Cannot send email to %s", to_email)
                raise RuntimeError("Email service unavailable. Please configure SMTP in production.")

            # Development / testing console logger
            logger.info(
                "\n==================== [DEV EMAIL SIMULATOR] ====================\n"
                "To: %s\nSubject: %s\n\n%s\n"
                "================================================================",
                to_email,
                subject,
                text_content,
            )
            return True

        # Send via SMTP
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{self.from_name} <{self.from_email}>"
        msg["To"] = to_email

        part1 = MIMEText(text_content, "plain")
        part2 = MIMEText(html_content, "html")
        msg.attach(part1)
        msg.attach(part2)

        try:
            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=10)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10)
                if self.use_tls:
                    server.starttls()

            if self.smtp_user and self.smtp_password:
                server.login(self.smtp_user, self.smtp_password)

            server.sendmail(self.from_email, [to_email], msg.as_string())
            server.quit()
            logger.info("Email successfully sent to %s | subject='%s'", to_email, subject)
            return True
        except Exception as exc:
            logger.error("Failed to deliver email to %s: %s", to_email, exc)
            if settings.is_production:
                raise RuntimeError(f"Email delivery failed: {exc}")
            return False

    def send_invitation_email(self, to_email: str, company_name: str, branch_name: str, role: str, raw_token: str) -> bool:
        """Send a corporate workspace invitation."""
        invite_url = f"{self.frontend_url}/accept-invite?token={raw_token}"
        subject = f"Invitation to join {company_name} on DMS"
        text_content = (
            f"Hello,\n\n"
            f"You have been invited to join {company_name} ({branch_name} branch) as a {role}.\n\n"
            f"To complete your account registration and set your secure password, visit:\n"
            f"{invite_url}\n\n"
            f"This link expires in {settings.INVITATION_EXPIRE_HOURS} hours.\n"
            f"If you did not expect this invitation, please ignore this email."
        )
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
            <h2 style="color: #0f172a;">Workspace Invitation</h2>
            <p>You have been invited to join <strong>{company_name}</strong> (Branch: <strong>{branch_name}</strong>) with the role of <strong>{role}</strong>.</p>
            <p>Please click the button below to accept your invitation and set up your password:</p>
            <div style="margin: 25px 0;">
                <a href="{invite_url}" style="background-color: #0284c7; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Accept Invitation</a>
            </div>
            <p style="color: #64748b; font-size: 14px;">Or copy and paste this link in your browser:<br><a href="{invite_url}">{invite_url}</a></p>
            <p style="color: #94a3b8; font-size: 12px; margin-top: 30px;">This invitation will expire in {settings.INVITATION_EXPIRE_HOURS} hours.</p>
        </div>
        """
        return self.send_email(to_email, subject, html_content, text_content)

    def send_branch_admin_activation_email(
        self, to_email: str, admin_name: str, company_name: str, branch_name: str, branch_code: str, raw_token: str
    ) -> bool:
        """Send primary branch administrator account activation email."""
        activation_url = f"{self.frontend_url}/accept-invite?token={raw_token}"
        subject = f"Activate your Administrator Account — {company_name} ({branch_name})"
        text_content = (
            f"Hello {admin_name},\n\n"
            f"You have been designated as the Primary Administrator for {branch_name} (Code: {branch_code}) "
            f"under {company_name} on the Document Management System (DMS).\n\n"
            f"As the Primary Branch Administrator, you will manage documents and branch users.\n\n"
            f"To activate your account and set your secure password, visit:\n"
            f"{activation_url}\n\n"
            f"This link expires in {settings.INVITATION_EXPIRE_HOURS} hours.\n"
            f"Once activated, you can sign in to the Branch Workspace at {self.frontend_url}/login.\n"
        )
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 620px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 8px; color: #1e293b;">
            <div style="background-color: #0f172a; padding: 16px; border-radius: 6px; margin-bottom: 20px; text-align: center;">
                <h1 style="color: #ffffff; margin: 0; font-size: 20px; font-weight: 700;">Document Management System</h1>
            </div>
            <h2 style="color: #0f172a; margin-top: 0;">Branch Administrator Activation</h2>
            <p>Dear <strong>{admin_name}</strong>,</p>
            <p>You have been assigned as the <strong>Primary Branch Administrator</strong> for <strong>{branch_name}</strong> (Branch Code: <code>{branch_code}</code>) under <strong>{company_name}</strong>.</p>
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 16px; margin: 20px 0;">
                <p style="margin: 0 0 6px 0; font-weight: 600; color: #334155;">Assigned Role &amp; Access:</p>
                <ul style="margin: 0; padding-left: 20px; color: #475569; font-size: 14px;">
                    <li>Branch: <strong>{branch_name} ({branch_code})</strong></li>
                    <li>Role: <strong>Branch Administrator (ADMIN)</strong></li>
                    <li>Permissions: Branch document management, indexing, invoice generation &amp; staff administration</li>
                </ul>
            </div>
            <p>Please click the button below to activate your account and choose your secure password:</p>
            <div style="margin: 25px 0; text-align: center;">
                <a href="{activation_url}" style="background-color: #ef233c; color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block; font-size: 15px;">Set Password &amp; Activate Account</a>
            </div>
            <p style="color: #64748b; font-size: 14px;">Or copy and paste this link in your browser:<br><a href="{activation_url}" style="color: #ef233c;">{activation_url}</a></p>
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;" />
            <p style="color: #94a3b8; font-size: 12px; margin: 0;">This activation link will expire in {settings.INVITATION_EXPIRE_HOURS} hours.</p>
        </div>
        """
        return self.send_email(to_email, subject, html_content, text_content)

    def send_password_reset_email(self, to_email: str, portal_name: str, raw_token: str) -> bool:
        """Send a password recovery email."""
        reset_url = f"{self.frontend_url}/reset-password?token={raw_token}"
        subject = f"Password Reset Request — DMS {portal_name.capitalize()} Portal"
        text_content = (
            f"Hello,\n\n"
            f"A password reset was requested for your account on the DMS {portal_name.capitalize()} Portal.\n\n"
            f"To reset your password, visit the following link:\n"
            f"{reset_url}\n\n"
            f"This link will expire in {settings.PASSWORD_RESET_EXPIRE_MINUTES} minutes.\n"
            f"If you did not request this, please disregard this email. Your password will remain unchanged."
        )
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
            <h2 style="color: #0f172a;">Password Reset Request</h2>
            <p>A request was received to reset the password for your account on the <strong>DMS {portal_name.capitalize()} Portal</strong>.</p>
            <div style="margin: 25px 0;">
                <a href="{reset_url}" style="background-color: #0284c7; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Reset Password</a>
            </div>
            <p style="color: #64748b; font-size: 14px;">Or copy and paste this link in your browser:<br><a href="{reset_url}">{reset_url}</a></p>
            <p style="color: #94a3b8; font-size: 12px; margin-top: 30px;">This link will expire in {settings.PASSWORD_RESET_EXPIRE_MINUTES} minutes. If you did not make this request, you can safely ignore this email.</p>
        </div>
        """
        return self.send_email(to_email, subject, html_content, text_content)

    def send_onboarding_invitation_email(self, to_email: str, contact_name: str, company_name: str, raw_token: str) -> bool:
        """Send onboarding registration link to the prospective company contact person."""
        onboarding_url = f"{self.frontend_url}/company/onboard?token={raw_token}"
        subject = f"Complete Company Onboarding for {company_name} — DMS"
        text_content = (
            f"Hello {contact_name},\n\n"
            f"You have been invited by the Platform Master Admin to register and onboard {company_name} onto the Document Management System (DMS).\n\n"
            f"Please complete your company onboarding registration by opening the following link:\n"
            f"{onboarding_url}\n\n"
            f"You will be asked to provide your official company details, Indian tax identifiers (PAN, GSTIN), registered address, authorized representative info, and first company administrator account.\n\n"
            f"If you have any questions, please contact your DMS Platform Administrator."
        )
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 620px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 8px; color: #1e293b;">
            <div style="background-color: #0284c7; padding: 16px; border-radius: 6px; margin-bottom: 20px; text-align: center;">
                <h1 style="color: #ffffff; margin: 0; font-size: 20px; font-weight: 700;">Document Management System</h1>
            </div>
            <h2 style="color: #0f172a; margin-top: 0;">Company Onboarding Application</h2>
            <p>Dear <strong>{contact_name}</strong>,</p>
            <p>You have been invited by the Master Administrator to register <strong>{company_name}</strong> on the DMS platform.</p>
            <p>Please click the button below to complete the onboarding form and upload the necessary verification documents:</p>
            <div style="margin: 25px 0; text-align: center;">
                <a href="{onboarding_url}" style="background-color: #0284c7; color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block; font-size: 15px;">Complete Onboarding Form</a>
            </div>
            <p style="color: #64748b; font-size: 14px;">Or copy and paste this link in your browser:<br><a href="{onboarding_url}" style="color: #0284c7;">{onboarding_url}</a></p>
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;" />
            <p style="color: #94a3b8; font-size: 12px; margin: 0;">This link is unique to your application. Please do not share it with unauthorized individuals.</p>
        </div>
        """
        return self.send_email(to_email, subject, html_content, text_content)

    def send_onboarding_changes_requested_email(self, to_email: str, contact_name: str, company_name: str, review_comment: str, raw_token: str) -> bool:
        """Send notification that Master Admin requested changes to the onboarding application."""
        onboarding_url = f"{self.frontend_url}/company/onboard?token={raw_token}"
        subject = f"Changes Requested: {company_name} Onboarding Application — DMS"
        text_content = (
            f"Hello {contact_name},\n\n"
            f"The Master Administrator has reviewed your onboarding application for {company_name} and requested changes before it can be approved.\n\n"
            f"Review Message from Master Admin:\n"
            f"----------------------------------------\n"
            f"{review_comment}\n"
            f"----------------------------------------\n\n"
            f"All your previously submitted details have been preserved. Please visit the link below to review, modify the requested details, and resubmit:\n"
            f"{onboarding_url}\n\n"
            f"Best regards,\nDMS Master Administration Team"
        )
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 620px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 8px; color: #1e293b;">
            <div style="background-color: #d97706; padding: 16px; border-radius: 6px; margin-bottom: 20px; text-align: center;">
                <h1 style="color: #ffffff; margin: 0; font-size: 20px; font-weight: 700;">Action Required: Changes Requested</h1>
            </div>
            <p>Dear <strong>{contact_name}</strong>,</p>
            <p>The Master Administrator has reviewed your onboarding application for <strong>{company_name}</strong> and requested updates:</p>
            <div style="background-color: #fef3c7; border-left: 4px solid #f59e0b; padding: 14px 18px; margin: 20px 0; border-radius: 4px;">
                <p style="margin: 0; font-weight: bold; color: #92400e; font-size: 13px; text-transform: uppercase;">Reviewer Feedback:</p>
                <p style="margin: 6px 0 0; color: #78350f; font-size: 14px; white-space: pre-wrap;">{review_comment}</p>
            </div>
            <p>All previously entered data is preserved. Please click the button below to update the requested information and resubmit your application:</p>
            <div style="margin: 25px 0; text-align: center;">
                <a href="{onboarding_url}" style="background-color: #d97706; color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block; font-size: 15px;">Update &amp; Resubmit Form</a>
            </div>
            <p style="color: #64748b; font-size: 14px;">Or open this link:<br><a href="{onboarding_url}" style="color: #d97706;">{onboarding_url}</a></p>
        </div>
        """
        return self.send_email(to_email, subject, html_content, text_content)

    def send_onboarding_approved_email(self, to_email: str, contact_name: str, company_name: str, admin_email: str) -> bool:
        """Send notification that company onboarding has been approved and account is live."""
        login_url = f"{self.frontend_url}/company/login"
        subject = f"Congratulations! {company_name} is Approved on DMS"
        text_content = (
            f"Hello {contact_name},\n\n"
            f"We are pleased to inform you that the onboarding application for {company_name} has been approved by the Master Administrator!\n\n"
            f"Your company account and initial workspace have been provisioned.\n"
            f"The first Company Administrator account is ready:\n"
            f"Login Email: {admin_email}\n"
            f"Portal: {login_url}\n\n"
            f"You can now sign in using the password specified during onboarding.\n\n"
            f"Welcome to DMS!"
        )
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 620px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 8px; color: #1e293b;">
            <div style="background-color: #16a34a; padding: 16px; border-radius: 6px; margin-bottom: 20px; text-align: center;">
                <h1 style="color: #ffffff; margin: 0; font-size: 20px; font-weight: 700;">Company Approved &amp; Live!</h1>
            </div>
            <p>Dear <strong>{contact_name}</strong>,</p>
            <p>We are pleased to inform you that your onboarding application for <strong>{company_name}</strong> has been <strong>approved</strong> by the Platform Master Administrator.</p>
            <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; padding: 16px; border-radius: 6px; margin: 20px 0;">
                <p style="margin: 0 0 8px; font-weight: bold; color: #166534;">First Company Administrator Details:</p>
                <p style="margin: 4px 0; color: #15803d;"><strong>Login Email:</strong> {admin_email}</p>
                <p style="margin: 4px 0; color: #15803d;"><strong>Password:</strong> As configured during registration</p>
                <p style="margin: 4px 0; color: #15803d;"><strong>Role:</strong> Global Company Administrator</p>
            </div>
            <div style="margin: 25px 0; text-align: center;">
                <a href="{login_url}" style="background-color: #16a34a; color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block; font-size: 15px;">Sign in to Company Portal</a>
            </div>
            <p style="color: #64748b; font-size: 14px;">Portal link:<br><a href="{login_url}" style="color: #16a34a;">{login_url}</a></p>
        </div>
        """
        return self.send_email(to_email, subject, html_content, text_content)

    def send_onboarding_rejected_email(self, to_email: str, contact_name: str, company_name: str, reason: str) -> bool:
        """Send notification of rejected onboarding application."""
        subject = f"Application Status Update: {company_name} — DMS"
        text_content = (
            f"Hello {contact_name},\n\n"
            f"Thank you for your interest in DMS. Following our review, we regret to inform you that the onboarding application for {company_name} could not be approved at this time.\n\n"
            f"Reason:\n{reason}\n\n"
            f"If you believe this was in error, please contact your DMS administrator.\n"
        )
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 620px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 8px; color: #1e293b;">
            <h2 style="color: #b91c1c; margin-top: 0;">Onboarding Application Status Update</h2>
            <p>Dear <strong>{contact_name}</strong>,</p>
            <p>Following review of the onboarding application for <strong>{company_name}</strong>, we regret to inform you that your application could not be approved at this time.</p>
            <div style="background-color: #fef2f2; border: 1px solid #fecaca; padding: 14px 18px; margin: 20px 0; border-radius: 4px;">
                <p style="margin: 0; font-weight: bold; color: #991b1b; font-size: 13px;">Reason:</p>
                <p style="margin: 6px 0 0; color: #7f1d1d; font-size: 14px;">{reason}</p>
            </div>
            <p>If you have questions or wish to provide additional information, please contact your DMS administrator.</p>
        </div>
        """
        return self.send_email(to_email, subject, html_content, text_content)


email_service = EmailService()
