# utils/csv_parser.py
import pandas as pd
import numpy as np
from datetime import datetime
from models import Instrument, Trade
from sqlalchemy.orm import Session

def parse_trade_csv(file_path, instrument_name, db_session):
    """Parse a CSV file and store trades in the database."""
    # Check if instrument exists, create if not
    instrument = db_session.query(Instrument).filter(Instrument.name == instrument_name).first()
    if not instrument:
        instrument = Instrument(name=instrument_name)
        db_session.add(instrument)
        db_session.commit()
    
    # Read the CSV - handle thousands separator in Price INR column
    df = pd.read_csv(
        file_path, 
        thousands=',',  # Handle comma as thousands separator
        converters={
            'Price INR': lambda x: float(x.replace(',', '').replace('"', '')), 
            'Profit %': lambda x: float(x.strip('%')),
            'Cumulative profit %': lambda x: float(x.strip('%')) if pd.notna(x) else None,
            'Run-up %': lambda x: float(x.strip('%')) if pd.notna(x) else None,
            'Drawdown %': lambda x: float(x.strip('%')) if pd.notna(x) else None
        }
    )
    
    # Process the data by trade number
    completed_trades = []  # Keep track of processed trades
    
    for trade_num, group in df.groupby('Trade #'):
        # Skip if we already processed this trade
        if trade_num in completed_trades:
            continue
            
        completed_trades.append(trade_num)
            
        # Find entry and exit rows
        entry_rows = group[group['Type'].str.contains('Entry', case=False)]
        exit_rows = group[group['Type'].str.contains('Exit', case=False)]
        
        # If we can't find explicit entry/exit rows, try using Long/Short for entry
        if len(entry_rows) == 0:
            # For Ins1.csv pattern, Long/Short might be the entry indicators
            long_rows = group[group['Type'].str.contains('Long', case=False)]
            short_rows = group[group['Type'].str.contains('Short', case=False)]
            
            if len(long_rows) > 0:
                # Find the row that isn't an exit (for entry)
                entry_rows = long_rows[~long_rows['Type'].str.contains('Exit', case=False)]
            elif len(short_rows) > 0:
                # Find the row that isn't an exit (for entry)
                entry_rows = short_rows[~short_rows['Type'].str.contains('Exit', case=False)]
        
        # Ensure we have one entry and one exit row
        if len(entry_rows) != 1 or len(exit_rows) != 1:
            print(f"Warning: Trade #{trade_num} doesn't have exactly one entry and one exit row")
            continue
            
        entry_row = entry_rows.iloc[0]
        exit_row = exit_rows.iloc[0]
        
        # Parse dates
        entry_datetime = pd.to_datetime(entry_row['Date/Time'])
        exit_datetime = pd.to_datetime(exit_row['Date/Time'])
        
        # Calculate holding time in hours
        holding_time = (exit_datetime - entry_datetime).total_seconds() / 3600
        
        # Determine trade type (Long or Short)
        if 'Long' in entry_row['Type']:
            entry_type = 'Long'
        elif 'Short' in entry_row['Type']:
            entry_type = 'Short'
        else:
            # Try to determine from the signal
            signal = entry_row['Signal'].lower()
            entry_type = 'Long' if 'buy' in signal else 'Short'
        
        # Convert numpy types to native Python types to avoid database errors
        def to_python_type(val):
            if isinstance(val, (np.integer, np.int64)):
                return int(val)
            elif isinstance(val, (np.floating, np.float64)):
                return float(val)
            elif isinstance(val, np.bool_):
                return bool(val)
            return val
            
        # Create trade object with properly converted types
        trade = Trade(
            trade_number=int(trade_num),  # Convert to int to avoid numpy.int64
            instrument_id=instrument.id,
            
            # Entry details
            entry_type=entry_type,
            entry_signal=str(entry_row['Signal']),
            entry_datetime=entry_datetime.to_pydatetime(),  # Convert pandas timestamp to Python datetime
            entry_price=float(entry_row['Price INR']),  # Ensure float
            
            # Exit details
            exit_type='Exit',
            exit_signal=str(exit_row['Signal']),
            exit_datetime=exit_datetime.to_pydatetime(),
            exit_price=float(exit_row['Price INR']),
            
            # Common details - convert all numeric values to Python native types
            contracts=int(entry_row['Contracts']),
            profit_inr=float(entry_row['Profit INR']),
            profit_percentage=float(entry_row['Profit %'].replace('%', '')) if isinstance(entry_row['Profit %'], str) else float(entry_row['Profit %']),
            
            # Handle optional columns that might be missing or have null values
            cumulative_profit_inr=to_python_type(entry_row.get('Cumulative profit INR', None)),
            cumulative_profit_percentage=to_python_type(entry_row.get('Cumulative profit %', None)),
            run_up_inr=to_python_type(entry_row.get('Run-up INR', None)),
            run_up_percentage=to_python_type(entry_row.get('Run-up %', None)),
            drawdown_inr=to_python_type(entry_row.get('Drawdown INR', None)),
            drawdown_percentage=to_python_type(entry_row.get('Drawdown %', None)),
            
            # Calculated fields
            holding_time_hours=float(holding_time)
        )
        
        try:
            db_session.add(trade)
            db_session.flush()  # Try to detect errors early
        except Exception as e:
            db_session.rollback()
            print(f"Error adding trade #{trade_num}: {str(e)}")
            raise e
    
    db_session.commit()
    return len(completed_trades)