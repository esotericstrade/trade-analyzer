# app.py
import os
from flask import Flask, request, render_template, redirect, url_for, flash
from werkzeug.utils import secure_filename
from database import init_db, get_db
from models import Instrument, Trade
from utils.csv_parser import parse_trade_csv
import pandas as pd
from datetime import datetime
from collections import defaultdict
from sqlalchemy import and_, func

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key")
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

app.config['APPLICATION_ROOT'] = '/trade-analyzer'

class PrefixMiddleware:
    def __init__(self, app, prefix='/'):
        self.app = app
        self.prefix = prefix

    def __call__(self, environ, start_response):
        if environ['PATH_INFO'].startswith(self.prefix):
            environ['PATH_INFO'] = environ['PATH_INFO'][len(self.prefix):]
            environ['SCRIPT_NAME'] = self.prefix
            return self.app(environ, start_response)
        else:
            start_response('404', [('Content-Type', 'text/plain')])
            return [b'Not Found']

app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix='/trade-analyzer')

# Initialize database
init_db()

@app.route('/')
def index():
    db = next(get_db())
    instruments = db.query(Instrument).all()
    return render_template('index.html', instruments=instruments)

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        # Check if an instrument name was provided
        instrument_name = request.form.get('instrument_name')
        if not instrument_name:
            flash('Please provide an instrument name', 'error')
            return redirect(request.url)
        
        # Check if a file was uploaded
        if 'file' not in request.files:
            flash('No file part', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'error')
            return redirect(request.url)
        
        if file and file.filename.endswith('.csv'):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            # Parse the CSV and add to database
            db = next(get_db())
            try:
                num_trades = parse_trade_csv(file_path, instrument_name, db)
                flash(f'Successfully imported {num_trades} trades for {instrument_name}', 'success')
            except Exception as e:
                import traceback
                traceback.print_exc()
                flash(f'Error importing CSV: {str(e)}', 'error')
            
            return redirect(url_for('index'))
        else:
            flash('File must be a CSV', 'error')
            return redirect(request.url)
    
    return render_template('upload.html')

@app.route('/instrument/<int:instrument_id>')
def instrument_details(instrument_id):
    db = next(get_db())
    instrument = db.query(Instrument).get(instrument_id)
    if not instrument:
        flash('Instrument not found', 'error')
        return redirect(url_for('index'))
    
    trades = db.query(Trade).filter(Trade.instrument_id == instrument_id).all()
    return render_template('instrument_details.html', instrument=instrument, trades=trades)

@app.route('/analysis')
def analysis():
    db = next(get_db())
    instruments = db.query(Instrument).all()
    return render_template('analysis.html', instruments=instruments)

@app.route('/analyze_drawdowns', methods=['POST'])
def analyze_drawdowns():
    selected_instruments = request.form.getlist('instruments')
    if not selected_instruments:
        flash('Please select at least one instrument', 'error')
        return redirect(url_for('analysis'))
    
    db = next(get_db())
    results = {}
    
    for inst_id in selected_instruments:
        instrument = db.query(Instrument).get(int(inst_id))
        trades = db.query(Trade).filter(Trade.instrument_id == int(inst_id)).all()
        
        # Calculate drawdowns and other metrics
        # This is simplified - you'll want to expand this based on your requirements
        max_drawdown = min([t.drawdown_percentage or 0 for t in trades], default=0)
        avg_drawdown = sum([t.drawdown_percentage or 0 for t in trades]) / len(trades) if trades else 0
        
        results[instrument.name] = {
            'max_drawdown': max_drawdown,
            'avg_drawdown': avg_drawdown,
            'trade_count': len(trades),
            'profitable_trades': len([t for t in trades if (t.profit_inr or 0) > 0]),
            'losing_trades': len([t for t in trades if (t.profit_inr or 0) <= 0]),
        }
    
    return render_template('drawdown_results.html', results=results)

@app.route('/analyze_cumulative', methods=['POST'])
def analyze_cumulative():
    selected_instruments = request.form.getlist('instruments')
    start_date_str = request.form.get('start_date')
    end_date_str = request.form.get('end_date')
    
    if not selected_instruments:
        flash('Please select at least one instrument', 'error')
        return redirect(url_for('analysis'))
    
    # Parse dates if provided
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d') if start_date_str else None
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d') if end_date_str else None
    
    db = next(get_db())
    
    # Get the instrument names and organize trades by instrument
    instrument_names = []
    instrument_trades = {}
    
    for inst_id in selected_instruments:
        instrument = db.query(Instrument).get(int(inst_id))
        if not instrument:
            continue
            
        instrument_names.append(instrument.name)
        
        # Get trades for this specific instrument within the date range
        inst_query = db.query(Trade).filter(Trade.instrument_id == int(inst_id))
        
        if start_date:
            inst_query = inst_query.filter(Trade.entry_datetime >= start_date)
        if end_date:
            inst_query = inst_query.filter(Trade.exit_datetime  <= end_date)
            
        instrument_trades[instrument.name] = inst_query.all()
    
    # Build the query to get all trades across instruments within the date range
    query = db.query(Trade).filter(Trade.instrument_id.in_([int(i) for i in selected_instruments]))
    
    if start_date:
        query = query.filter(Trade.entry_datetime >= start_date)
    if end_date:
        query = query.filter(Trade.exit_datetime  <= end_date)
    
    trades = query.all()
    
    # Calculate cumulative metrics
    total_trades = len(trades)
    winning_trades = len([t for t in trades if (t.profit_inr or 0) > 0])
    losing_trades = total_trades - winning_trades
    win_rate = (winning_trades / total_trades * 100) if total_trades else 0
    
    # Calculate profit metrics
    total_profit = sum([t.profit_inr or 0 for t in trades])
    avg_profit = total_profit / total_trades if total_trades else 0
    
    # Calculate average win and loss
    wins = [t.profit_inr or 0 for t in trades if (t.profit_inr or 0) > 0]
    losses = [t.profit_inr or 0 for t in trades if (t.profit_inr or 0) <= 0]
    
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    
    # Prepare cumulative results
    cumulative_results = {
        'total_trades': total_trades,
        'winning_trades': winning_trades,
        'losing_trades': losing_trades,
        'win_rate': win_rate,
        'total_profit': total_profit,
        'avg_profit': avg_profit,
        'avg_win': avg_win,
        'avg_loss': avg_loss
    }
    
    # Calculate monthly breakdown
    monthly_data = []
    monthly_trades = defaultdict(list)
    
    for trade in trades:
        month_year = trade.entry_datetime.strftime('%B %Y')
        monthly_trades[month_year].append(trade)
    
    # Sort months chronologically
    sorted_months = sorted(monthly_trades.keys(), 
                          key=lambda x: datetime.strptime(x, '%B %Y'))
    
    for month in sorted_months:
        month_trades = monthly_trades[month]
        month_total = len(month_trades)
        month_wins = len([t for t in month_trades if (t.profit_inr or 0) > 0])
        month_win_rate = (month_wins / month_total * 100) if month_total else 0
        month_profit = sum([t.profit_inr or 0 for t in month_trades])
        
        monthly_data.append({
            'month_year': month,
            'total_trades': month_total,
            'winning_trades': month_wins,
            'win_rate': month_win_rate,
            'total_profit': month_profit
        })
    
    current_datetime = datetime.now()

    return render_template(
        'cumulative_results.html',
        selected_instruments=instrument_names,
        start_date=start_date,
        end_date=end_date,
        cumulative=cumulative_results,
        monthly_data=monthly_data,
        instrument_trades=instrument_trades,
        current_datetime=current_datetime
    )

if __name__ == '__main__':
    app.run(debug=True)