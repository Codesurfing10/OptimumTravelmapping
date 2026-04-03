import os


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///space_exchange.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
    WEB3_PROVIDER_URL = os.environ.get('WEB3_PROVIDER_URL', 'https://mainnet.infura.io/v3/YOUR_KEY')
    SMART_CONTRACT_ADDRESS = os.environ.get('SMART_CONTRACT_ADDRESS', '')
