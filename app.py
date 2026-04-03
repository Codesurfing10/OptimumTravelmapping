import os
import json
import stripe
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from dotenv import load_dotenv
from config import Config
from models import db, ResourceCategory, Contract, Transaction

load_dotenv()

app = Flask(__name__)
app.config.from_object(Config)

# Fix postgres:// -> postgresql:// for SQLAlchemy compatibility
db_url = app.config['SQLALCHEMY_DATABASE_URI']
if db_url and db_url.startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url.replace('postgres://', 'postgresql://', 1)

db.init_app(app)
stripe.api_key = app.config['STRIPE_SECRET_KEY']


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

CATEGORIES_SEED = [
    {
        'name': 'Lunar Water Ice',
        'slug': 'lunar-water-ice',
        'description': 'Water ice deposits found in permanently shadowed craters near the lunar poles. Essential for life support, rocket propellant, and lunar base operations.',
        'icon_emoji': '🌊',
        'unit': 'tonnes',
        'current_price_usd': 500.0,
        'price_change_24h': 2.4,
    },
    {
        'name': 'Helium-3',
        'slug': 'helium-3',
        'description': 'Rare isotope embedded in the lunar regolith by solar wind. Prized as a fuel for future nuclear fusion reactors with virtually no radioactive waste.',
        'icon_emoji': '⚛️',
        'unit': 'kg',
        'current_price_usd': 40000.0,
        'price_change_24h': -1.2,
    },
    {
        'name': 'Lunar Regolith Iron',
        'slug': 'lunar-regolith-iron',
        'description': 'Iron extracted from lunar regolith via in-situ resource utilization. Key structural material for constructing lunar infrastructure.',
        'icon_emoji': '🔩',
        'unit': 'tonnes',
        'current_price_usd': 8000.0,
        'price_change_24h': 0.8,
    },
    {
        'name': 'Platinum Group Metals',
        'slug': 'platinum-group-metals',
        'description': 'High-concentration platinum, palladium, and osmium from metallic asteroids. Far exceeds Earth deposits and critical for industrial catalysis.',
        'icon_emoji': '💎',
        'unit': 'kg',
        'current_price_usd': 35000.0,
        'price_change_24h': 3.1,
    },
    {
        'name': 'Titanium Ore',
        'slug': 'titanium-ore',
        'description': 'Ilmenite-rich deposits found in lunar mare basalts. Lightweight, corrosion-resistant metal vital for spacecraft and habitat construction.',
        'icon_emoji': '🪨',
        'unit': 'tonnes',
        'current_price_usd': 12000.0,
        'price_change_24h': -0.5,
    },
    {
        'name': 'Rare Earth Elements',
        'slug': 'rare-earth-elements',
        'description': 'Neodymium, dysprosium, and other lanthanides from asteroid and lunar sources. Critical for advanced electronics, magnets, and propulsion systems.',
        'icon_emoji': '🌟',
        'unit': 'kg',
        'current_price_usd': 2500.0,
        'price_change_24h': 1.7,
    },
    {
        'name': 'Silicon (Solar Grade)',
        'slug': 'silicon-solar-grade',
        'description': 'High-purity silicon refined from lunar regolith for in-space solar panel manufacturing. Enables large-scale space-based solar power infrastructure.',
        'icon_emoji': '☀️',
        'unit': 'tonnes',
        'current_price_usd': 15000.0,
        'price_change_24h': -2.3,
    },
    {
        'name': 'Carbon (Asteroid)',
        'slug': 'carbon-asteroid',
        'description': 'Carbonaceous material from C-type asteroids including organic compounds. Used for life support consumables, plastics, and carbon-fiber composites.',
        'icon_emoji': '🌑',
        'unit': 'tonnes',
        'current_price_usd': 3000.0,
        'price_change_24h': 0.3,
    },
]


def seed_data():
    if ResourceCategory.query.count() > 0:
        return

    categories = {}
    for cat_data in CATEGORIES_SEED:
        cat = ResourceCategory(**cat_data)
        db.session.add(cat)
        db.session.flush()
        categories[cat.slug] = cat

    now = datetime.utcnow()

    sample_contracts = [
        {
            'title': 'Lunar Water Ice Option — Shackleton Crater Deposit',
            'contract_type': 'OPTION',
            'category_slug': 'lunar-water-ice',
            'resource_quantity': 50.0,
            'strike_price_usd': 480.0,
            'expiry_date': now + timedelta(days=90),
            'premium_usd': 2400.0,
            'seller_name': 'AriaMoon Resources LLC',
            'seller_wallet': '0xA1b2C3d4E5f6A7b8C9d0E1f2A3b4C5d6E7f8A9b0',
            'status': 'OPEN',
            'payment_method': 'BOTH',
            'description': 'Call option on 50 tonnes of confirmed Shackleton Crater water ice. Strike set 4% below current market. Excellent entry for lunar fuel-depot plays.',
        },
        {
            'title': 'Helium-3 Forward Contract — 6-Month Delivery',
            'contract_type': 'FORWARD',
            'category_slug': 'helium-3',
            'resource_quantity': 2.5,
            'strike_price_usd': 39500.0,
            'expiry_date': now + timedelta(days=180),
            'premium_usd': 12000.0,
            'seller_name': 'FusionFrontier Trading',
            'seller_wallet': '0xB2c3D4e5F6a7B8c9D0e1F2a3B4c5D6e7F8a9B0c1',
            'status': 'OPEN',
            'payment_method': 'CRYPTO',
            'description': 'Forward delivery of 2.5 kg He-3 from Oceanus Procellarum mining operation. Fixed-price certainty for fusion-reactor pilot programs.',
        },
        {
            'title': 'Platinum Group Metals Option — Psyche-Class Asteroid',
            'contract_type': 'OPTION',
            'category_slug': 'platinum-group-metals',
            'resource_quantity': 10.0,
            'strike_price_usd': 34000.0,
            'expiry_date': now + timedelta(days=120),
            'premium_usd': 18500.0,
            'seller_name': 'AsteroidVault Inc.',
            'seller_wallet': '0xC3d4E5f6A7b8C9d0E1f2A3b4C5d6E7f8A9b0C1d2',
            'status': 'OPEN',
            'payment_method': 'BOTH',
            'description': 'Option to purchase 10 kg of mixed PGM concentrate extracted from a Psyche-class metallic asteroid. Includes platinum, palladium, and iridium fractions.',
        },
        {
            'title': 'Lunar Regolith Iron Forward — Mare Tranquillitatis',
            'contract_type': 'FORWARD',
            'category_slug': 'lunar-regolith-iron',
            'resource_quantity': 200.0,
            'strike_price_usd': 7800.0,
            'expiry_date': now + timedelta(days=270),
            'premium_usd': 5000.0,
            'seller_name': 'SeleneSteel Co.',
            'seller_wallet': '0xD4e5F6a7B8c9D0e1F2a3B4c5D6e7F8a9B0c1D2e3',
            'status': 'OPEN',
            'payment_method': 'STRIPE',
            'description': 'Guaranteed forward delivery of 200 tonnes of ISRU-refined iron from Mare Tranquillitatis. Certified for structural-grade applications in cislunar construction.',
        },
        {
            'title': 'Rare Earth Elements Option — Lunar Highlands',
            'contract_type': 'OPTION',
            'category_slug': 'rare-earth-elements',
            'resource_quantity': 500.0,
            'strike_price_usd': 2450.0,
            'expiry_date': now + timedelta(days=60),
            'premium_usd': 8750.0,
            'seller_name': 'LunarLanthanides Ltd.',
            'seller_wallet': '0xE5f6A7b8C9d0E1f2A3b4C5d6E7f8A9b0C1d2E3f4',
            'status': 'OPEN',
            'payment_method': 'BOTH',
            'description': 'Call option on 500 kg of mixed rare earth concentrate including Nd, Dy, and Eu fractions. Positioned for demand from next-gen spacecraft propulsion manufacturing.',
        },
        {
            'title': 'Solar-Grade Silicon Forward — Regolith Refinery Alpha',
            'contract_type': 'FORWARD',
            'category_slug': 'silicon-solar-grade',
            'resource_quantity': 30.0,
            'strike_price_usd': 14800.0,
            'expiry_date': now + timedelta(days=365),
            'premium_usd': 9000.0,
            'seller_name': 'SolarScape Industries',
            'seller_wallet': '0xF6a7B8c9D0e1F2a3B4c5D6e7F8a9B0c1D2e3F4a5',
            'status': 'OPEN',
            'payment_method': 'CRYPTO',
            'description': 'One-year forward on 30 tonnes of 99.999% pure solar-grade silicon produced at Refinery Alpha, Shackleton Rim. Ideal for in-space photovoltaic array construction.',
        },
        {
            'title': 'Titanium Ore Option — Copernicus Impact Basin',
            'contract_type': 'OPTION',
            'category_slug': 'titanium-ore',
            'resource_quantity': 75.0,
            'strike_price_usd': 11500.0,
            'expiry_date': now + timedelta(days=150),
            'premium_usd': 6200.0,
            'seller_name': 'TitanQuest Mining',
            'seller_wallet': '0xA7b8C9d0E1f2A3b4C5d6E7f8A9b0C1d2E3f4A5b6',
            'status': 'FILLED',
            'payment_method': 'BOTH',
            'description': 'FILLED — Call option on 75 tonnes ilmenite-rich titanium ore from Copernicus Basin high-grade seam. Strike price offered compelling discount at time of execution.',
        },
        {
            'title': 'Carbon (Asteroid) Forward — Ryugu Sample Return Program',
            'contract_type': 'FORWARD',
            'category_slug': 'carbon-asteroid',
            'resource_quantity': 150.0,
            'strike_price_usd': 3100.0,
            'expiry_date': now + timedelta(days=200),
            'premium_usd': 3500.0,
            'seller_name': 'CarbonCosmos Trading',
            'seller_wallet': '0xB8c9D0e1F2a3B4c5D6e7F8a9B0c1D2e3F4a5B6c7',
            'status': 'OPEN',
            'payment_method': 'STRIPE',
            'description': 'Forward on 150 tonnes of carbonaceous chondrite material sourced from Ryugu-class asteroid intercept. Rich in organics and hydrated silicates.',
        },
        {
            'title': 'Helium-3 Option — Aristarchus Plateau Hotspot',
            'contract_type': 'OPTION',
            'category_slug': 'helium-3',
            'resource_quantity': 1.0,
            'strike_price_usd': 41000.0,
            'expiry_date': now + timedelta(days=30),
            'premium_usd': 5500.0,
            'seller_name': 'FusionFrontier Trading',
            'seller_wallet': '0xB2c3D4e5F6a7B8c9D0e1F2a3B4c5D6e7F8a9B0c1',
            'status': 'EXPIRED',
            'payment_method': 'BOTH',
            'description': 'EXPIRED — Short-dated call option on 1 kg He-3 from Aristarchus Plateau high-flux zone. Contract expired unexercised.',
        },
        {
            'title': 'Lunar Water Ice Forward — Haworth Crater Bulk Supply',
            'contract_type': 'FORWARD',
            'category_slug': 'lunar-water-ice',
            'resource_quantity': 500.0,
            'strike_price_usd': 495.0,
            'expiry_date': now + timedelta(days=540),
            'premium_usd': 15000.0,
            'seller_name': 'PolarDawn Logistics',
            'seller_wallet': '0xC9d0E1f2A3b4C5d6E7f8A9b0C1d2E3f4A5b6C7d8',
            'status': 'OPEN',
            'payment_method': 'BOTH',
            'description': 'Bulk 18-month forward for 500 tonnes of processed water ice from Haworth Crater extraction facility. Competitive fixed price for long-range lunar mission planners.',
        },
    ]

    for c in sample_contracts:
        slug = c.pop('category_slug')
        cat = categories[slug]
        contract = Contract(
            category_id=cat.id,
            unit=cat.unit,
            current_market_price_usd=cat.current_price_usd,
            **c,
        )
        db.session.add(contract)

    db.session.commit()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    featured = Contract.query.filter_by(status='OPEN').limit(3).all()
    categories = ResourceCategory.query.all()
    total_contracts = Contract.query.count()
    open_options = Contract.query.filter_by(status='OPEN', contract_type='OPTION').count()
    open_forwards = Contract.query.filter_by(status='OPEN', contract_type='FORWARD').count()
    total_volume = db.session.query(db.func.sum(Transaction.amount_usd)).scalar() or 0.0
    stats = {
        'total_contracts': total_contracts,
        'open_options': open_options,
        'open_forwards': open_forwards,
        'total_volume': total_volume,
    }
    return render_template('index.html', featured=featured, categories=categories, stats=stats)


@app.route('/marketplace')
def marketplace():
    category_slug = request.args.get('category', '')
    contract_type = request.args.get('contract_type', '')
    status = request.args.get('status', '')

    query = Contract.query
    if category_slug:
        cat = ResourceCategory.query.filter_by(slug=category_slug).first()
        if cat:
            query = query.filter_by(category_id=cat.id)
    if contract_type:
        query = query.filter_by(contract_type=contract_type)
    if status:
        query = query.filter_by(status=status)

    contracts = query.order_by(Contract.created_at.desc()).all()
    categories = ResourceCategory.query.all()
    return render_template('marketplace.html', contracts=contracts, categories=categories,
                           selected_category=category_slug, selected_type=contract_type,
                           selected_status=status)


@app.route('/categories')
def categories():
    cats = ResourceCategory.query.all()
    return render_template('categories.html', categories=cats)


@app.route('/category/<slug>')
def category_detail(slug):
    cat = ResourceCategory.query.filter_by(slug=slug).first_or_404()
    contracts = Contract.query.filter_by(category_id=cat.id).order_by(Contract.created_at.desc()).all()
    return render_template('category_detail.html', category=cat, contracts=contracts)


@app.route('/contract/<int:contract_id>')
def contract_detail(contract_id):
    contract = Contract.query.get_or_404(contract_id)
    related = (Contract.query
               .filter_by(category_id=contract.category_id, status='OPEN')
               .filter(Contract.id != contract_id)
               .limit(3).all())
    stripe_key = app.config.get('STRIPE_PUBLISHABLE_KEY', '')
    return render_template('contract_detail.html', contract=contract, related=related,
                           stripe_key=stripe_key)


@app.route('/create', methods=['GET', 'POST'])
def create_contract():
    categories = ResourceCategory.query.all()
    if request.method == 'POST':
        try:
            cat_id = int(request.form['category_id'])
            cat = ResourceCategory.query.get_or_404(cat_id)
            expiry_str = request.form['expiry_date']
            expiry_dt = datetime.strptime(expiry_str, '%Y-%m-%d')

            contract = Contract(
                title=request.form['title'],
                contract_type=request.form['contract_type'],
                category_id=cat_id,
                resource_quantity=float(request.form['resource_quantity']),
                unit=cat.unit,
                strike_price_usd=float(request.form['strike_price_usd']),
                current_market_price_usd=cat.current_price_usd,
                expiry_date=expiry_dt,
                premium_usd=float(request.form['premium_usd']),
                seller_name=request.form['seller_name'],
                seller_wallet=request.form['seller_wallet'],
                payment_method=request.form['payment_method'],
                description=request.form.get('description', ''),
                status='OPEN',
            )
            db.session.add(contract)
            db.session.commit()
            flash('Contract created successfully!', 'success')
            return redirect(url_for('contract_detail', contract_id=contract.id))
        except Exception:
            flash('Error creating contract. Please check your inputs and try again.', 'danger')

    return render_template('create_contract.html', categories=categories)


@app.route('/dashboard')
def dashboard():
    contracts = Contract.query.order_by(Contract.created_at.desc()).all()
    transactions = Transaction.query.order_by(Transaction.created_at.desc()).all()
    stats = {
        'total': Contract.query.count(),
        'open': Contract.query.filter_by(status='OPEN').count(),
        'filled': Contract.query.filter_by(status='FILLED').count(),
        'expired': Contract.query.filter_by(status='EXPIRED').count(),
    }
    return render_template('dashboard.html', contracts=contracts, transactions=transactions, stats=stats)


@app.route('/wallet')
def wallet():
    smart_contract_address = app.config.get('SMART_CONTRACT_ADDRESS', '')
    transactions = Transaction.query.filter_by(payment_method='CRYPTO').order_by(Transaction.created_at.desc()).all()
    return render_template('wallet.html', smart_contract_address=smart_contract_address,
                           transactions=transactions)


@app.route('/checkout/<int:contract_id>')
def checkout(contract_id):
    contract = Contract.query.get_or_404(contract_id)
    stripe_key = app.config.get('STRIPE_PUBLISHABLE_KEY', '')
    return render_template('checkout.html', contract=contract, stripe_key=stripe_key)


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.route('/api/create-checkout-session', methods=['POST'])
def create_checkout_session():
    data = request.get_json()
    contract_id = data.get('contract_id')
    contract = Contract.query.get(contract_id)
    if not contract:
        return jsonify({'error': 'Contract not found'}), 404

    if not app.config.get('STRIPE_SECRET_KEY'):
        return jsonify({'error': 'Stripe not configured'}), 400

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': contract.title,
                        'description': f'{contract.contract_type} contract — {contract.resource_quantity} {contract.unit} @ ${contract.strike_price_usd:,.2f}/{contract.unit}',
                    },
                    'unit_amount': int(contract.premium_usd * 100),
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=request.host_url + f'contract/{contract_id}?payment=success',
            cancel_url=request.host_url + f'contract/{contract_id}?payment=cancelled',
            metadata={'contract_id': str(contract_id)},
        )

        txn = Transaction(
            contract_id=contract_id,
            buyer_email=data.get('email', ''),
            amount_usd=contract.premium_usd,
            payment_method='STRIPE',
            stripe_session_id=session.id,
            status='PENDING',
        )
        db.session.add(txn)
        db.session.commit()

        return jsonify({'url': session.url})
    except stripe.error.StripeError:
        return jsonify({'error': 'Payment processing failed. Please try again.'}), 400


@app.route('/api/payment-success', methods=['POST'])
def payment_success_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature', '')
    webhook_secret = app.config.get('STRIPE_WEBHOOK_SECRET', '')

    if not webhook_secret:
        return jsonify({'error': 'Webhook secret not configured'}), 400

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        return jsonify({'error': 'Invalid webhook signature'}), 400

    if event['type'] == 'checkout.session.completed':
        session_obj = event['data']['object']
        contract_id = int(session_obj['metadata'].get('contract_id', 0))
        txn = Transaction.query.filter_by(stripe_session_id=session_obj['id']).first()
        if txn:
            txn.status = 'COMPLETED'
            contract = Contract.query.get(contract_id)
            if contract:
                contract.status = 'FILLED'
            db.session.commit()

    return jsonify({'status': 'ok'})


@app.route('/api/contracts', methods=['GET'])
def api_list_contracts():
    status = request.args.get('status', '')
    contract_type = request.args.get('contract_type', '')
    query = Contract.query
    if status:
        query = query.filter_by(status=status)
    if contract_type:
        query = query.filter_by(contract_type=contract_type)
    contracts = query.all()
    return jsonify([c.to_dict() for c in contracts])


@app.route('/api/contracts', methods=['POST'])
def api_create_contract():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    try:
        cat = ResourceCategory.query.get(int(data['category_id']))
        if not cat:
            return jsonify({'error': 'Category not found'}), 404
        expiry_dt = datetime.fromisoformat(data['expiry_date'])
        contract = Contract(
            title=data['title'],
            contract_type=data['contract_type'],
            category_id=cat.id,
            resource_quantity=float(data['resource_quantity']),
            unit=cat.unit,
            strike_price_usd=float(data['strike_price_usd']),
            current_market_price_usd=cat.current_price_usd,
            expiry_date=expiry_dt,
            premium_usd=float(data['premium_usd']),
            seller_name=data['seller_name'],
            seller_wallet=data['seller_wallet'],
            payment_method=data.get('payment_method', 'BOTH'),
            description=data.get('description', ''),
            status='OPEN',
        )
        db.session.add(contract)
        db.session.commit()
        return jsonify(contract.to_dict()), 201
    except (KeyError, ValueError):
        return jsonify({'error': 'Invalid or missing required fields.'}), 400
    except Exception:
        return jsonify({'error': 'Failed to create contract.'}), 400


@app.route('/api/categories', methods=['GET'])
def api_list_categories():
    cats = ResourceCategory.query.all()
    return jsonify([c.to_dict() for c in cats])


@app.route('/api/market-data', methods=['GET'])
def api_market_data():
    import random
    cats = ResourceCategory.query.all()
    data = {}
    for cat in cats:
        fluctuation = random.uniform(-0.02, 0.02)
        data[cat.slug] = {
            'name': cat.name,
            'slug': cat.slug,
            'icon_emoji': cat.icon_emoji,
            'unit': cat.unit,
            'current_price_usd': round(cat.current_price_usd * (1 + fluctuation), 2),
            'price_change_24h': round(cat.price_change_24h + random.uniform(-0.3, 0.3), 2),
        }
    return jsonify(data)


@app.route('/api/crypto-purchase', methods=['POST'])
def api_crypto_purchase():
    data = request.get_json()
    contract_id = data.get('contract_id')
    contract = Contract.query.get(contract_id)
    if not contract:
        return jsonify({'error': 'Contract not found'}), 404

    txn = Transaction(
        contract_id=contract_id,
        buyer_wallet=data.get('buyer_wallet', ''),
        amount_usd=contract.premium_usd,
        payment_method='CRYPTO',
        tx_hash=data.get('tx_hash', ''),
        status='PENDING',
    )
    db.session.add(txn)
    contract.status = 'FILLED'
    db.session.commit()
    return jsonify({'status': 'ok', 'transaction_id': txn.id})


# ---------------------------------------------------------------------------
# App initialization
# ---------------------------------------------------------------------------

with app.app_context():
    db.create_all()
    seed_data()

if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG', 'false').lower() == 'true')
