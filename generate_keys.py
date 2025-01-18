import secrets

def generate_secret_key():
    return ''.join(secrets.choice('abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)') for i in range(50))


if __name__ == "__main__":
    secret_key = generate_secret_key()
    
    env_content = f"""
SECRET_KEY={secret_key}
REDIS_PASSWORD=your-redis-password
# Email settings
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@example.com
EMAIL_HOST_PASSWORD=pgpj pifx ghot yihn
# to get EMAIL_HOST_PASSWORD follow this link : https://www.geeksforgeeks.org/setup-sending-email-in-django-project/

# Stripe settings
STRIPE_PUBLISHABLE_KEY=pk_test_your-stripe-publishable-key
STRIPE_SECRET_KEY=your-stripe-secret-key
STRIPE_WEBHOOK_SECRET=whsec_your-stripe-webhook-secret
"""
    
    with open(".env", "w") as env_file:
        env_file.write(env_content)
    
    print("The .env file has been created with the generated keys and email configuration.")