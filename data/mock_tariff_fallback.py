"""
Deterministic generator for Spain (ES) Day-Ahead Electricity Prices.
Models authentic Spanish OMIE / ENTSO-E hourly spot price dynamics:
- Night off-peak: ~45-65 €/MWh
- Morning industrial ramp: ~80-110 €/MWh
- Solar PV midday depression ("solar duck curve"): ~15-45 €/MWh
- Evening peak: ~95-145 €/MWh
"""

import os
import datetime
import numpy as np
import pandas as pd


def generate_spain_tariffs(days=30, output_path=None):
    if output_path is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        output_path = os.path.join(base_dir, "electricity_prices_es.csv")

    np.random.seed(42)  # Deterministic repeatability
    
    # 30 days of hourly data ending today
    end_time = datetime.datetime.now(datetime.timezone.utc).replace(minute=0, second=0, microsecond=0)
    start_time = end_time - datetime.timedelta(days=days)
    
    timestamps = pd.date_range(start=start_time, end=end_time, freq="h")
    
    prices_mwh = []
    
    # Diurnal multiplier pattern (hour 0 to 23) in Spain
    hourly_pattern = [
        52.0, 48.0, 45.0, 44.0, 46.0, 55.0,  # 00-05 Night
        75.0, 92.0, 108.0, 98.0, 70.0, 42.0, # 06-11 Morning ramp & Solar start
        28.0, 22.0, 20.0, 24.0, 35.0, 65.0, # 12-17 Midday Solar depression
        95.0, 125.0, 138.0, 115.0, 85.0, 62.0 # 18-23 Evening peak & transition
    ]
    
    for ts in timestamps:
        hr = ts.hour
        weekday = ts.weekday()
        base_price = hourly_pattern[hr]
        
        # Weekend industrial demand reduction (-15%)
        if weekday >= 5:
            base_price *= 0.85
            
        # Add realistic noise and weekly macro trend
        noise = np.random.normal(0, 4.5)
        macro_swing = 8.0 * np.sin(2 * np.pi * (ts.day) / 7.0)
        
        price = max(2.5, base_price + macro_swing + noise)
        prices_mwh.append(round(price, 2))
        
    df = pd.DataFrame({
        "timestamp_utc": timestamps.strftime("%Y-%m-%d %H:%M:%S"),
        "price_eur_per_mwh": prices_mwh,
        "price_eur_per_kwh": [round(p / 1000.0, 5) for p in prices_mwh]
    })
    
    df.to_csv(output_path, index=False)
    print(f"Generated {len(df)} hourly tariff records -> {output_path}")
    print(f"Summary: Min={df['price_eur_per_mwh'].min():.2f} €/MWh, "
          f"Mean={df['price_eur_per_mwh'].mean():.2f} €/MWh, "
          f"Max={df['price_eur_per_mwh'].max():.2f} €/MWh")
    return df


if __name__ == "__main__":
    generate_spain_tariffs()
