from core.tasks import send_email

class EmailService:
    """
    Service to handle email-related operations, such as sending OTP and other custom emails.
    """
    
    def send_otp_email(self, otp, email):
        """
        Send OTP code to the user's email with a formatted message.
        Args:
            otp (str): The OTP code to send.
            email (str): The recipient's email address.
        """
        subject = "Your OTP Code"
        message = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #4CAF50;">Your OTP Code</h2>
            <p>Dear User,</p>
            <p>We received a request to verify your email address. Use the OTP code below to complete the process:</p>
            <p style="font-size: 1.5em; font-weight: bold; color: #4CAF50;">{otp}</p>
            <p>If you did not request this, please ignore this email.</p>
            <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
            <footer style="font-size: 0.9em; color: #777;">
                <p>Thank you for choosing our service!</p>
                <p>&copy; {2025} Project Planner. All rights reserved.</p>
            </footer>
        </body>
        </html>
        """
        send_email.delay(subject, message, email, content_type="text/html")

    def send_custom_email(self, subject, message_body, email):
        """
        Send a multi-purpose email.
        Args:
            subject (str): The subject of the email.
            message_body (str): The HTML content of the email.
            email (str): The recipient's email address.
        """
        message = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            {message_body}
            <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
            <footer style="font-size: 0.9em; color: #777;">
                <p>Thank you for choosing our service!</p>
                <p>&copy; {2025} Project Planner. All rights reserved.</p>
            </footer>
        </body>
        </html>
        """
        send_email.delay(subject, message, email, content_type="text/html")
