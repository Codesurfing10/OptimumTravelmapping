from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class ResourceCategory(db.Model):
    __tablename__ = 'resource_categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False)
    icon_emoji = db.Column(db.String(10), nullable=False)
    unit = db.Column(db.String(50), nullable=False)
    current_price_usd = db.Column(db.Float, nullable=False)
    price_change_24h = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    contracts = db.relationship('Contract', backref='category', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'description': self.description,
            'icon_emoji': self.icon_emoji,
            'unit': self.unit,
            'current_price_usd': self.current_price_usd,
            'price_change_24h': self.price_change_24h,
            'created_at': self.created_at.isoformat(),
        }


class Contract(db.Model):
    __tablename__ = 'contracts'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    contract_type = db.Column(db.String(20), nullable=False)  # OPTION or FORWARD
    category_id = db.Column(db.Integer, db.ForeignKey('resource_categories.id'), nullable=False)
    resource_quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(50), nullable=False)
    strike_price_usd = db.Column(db.Float, nullable=False)
    current_market_price_usd = db.Column(db.Float, nullable=False)
    expiry_date = db.Column(db.DateTime, nullable=False)
    premium_usd = db.Column(db.Float, nullable=False)
    seller_name = db.Column(db.String(100), nullable=False)
    seller_wallet = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), default='OPEN')  # OPEN, FILLED, EXPIRED
    payment_method = db.Column(db.String(20), default='BOTH')  # CRYPTO, STRIPE, BOTH
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    transactions = db.relationship('Transaction', backref='contract', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'contract_type': self.contract_type,
            'category_id': self.category_id,
            'category_name': self.category.name if self.category else None,
            'category_slug': self.category.slug if self.category else None,
            'resource_quantity': self.resource_quantity,
            'unit': self.unit,
            'strike_price_usd': self.strike_price_usd,
            'current_market_price_usd': self.current_market_price_usd,
            'expiry_date': self.expiry_date.isoformat(),
            'premium_usd': self.premium_usd,
            'seller_name': self.seller_name,
            'seller_wallet': self.seller_wallet,
            'status': self.status,
            'payment_method': self.payment_method,
            'description': self.description,
            'created_at': self.created_at.isoformat(),
        }


class Transaction(db.Model):
    __tablename__ = 'transactions'

    id = db.Column(db.Integer, primary_key=True)
    contract_id = db.Column(db.Integer, db.ForeignKey('contracts.id'), nullable=False)
    buyer_wallet = db.Column(db.String(200), nullable=True)
    buyer_email = db.Column(db.String(200), nullable=True)
    amount_usd = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(20), nullable=False)
    tx_hash = db.Column(db.String(200), nullable=True)
    stripe_session_id = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(20), default='PENDING')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'contract_id': self.contract_id,
            'buyer_wallet': self.buyer_wallet,
            'buyer_email': self.buyer_email,
            'amount_usd': self.amount_usd,
            'payment_method': self.payment_method,
            'tx_hash': self.tx_hash,
            'stripe_session_id': self.stripe_session_id,
            'status': self.status,
            'created_at': self.created_at.isoformat(),
        }
