import requests
import sqlite3
import pandas as pd
from tqdm import tqdm

SQLITE_DB_FILE = "sensibull.db"


def get_io(script):
    url = f"https://oxide.sensibull.com/v1/compute/iv_chart/{script}"
    session = requests.session()
    req = session.get(url)
    req.raise_for_status()
    data = req.json()['payload']
    ois = []
    for date in data['iv_ohlc_data']:
        oi = data['iv_ohlc_data'][date]
        oi['date'] = date
        oi['script'] = script
        ois.append(oi)
    return pd.DataFrame(ois)

def get_options():
    import requests 
    session = requests.Session()
    api_url = "https://oxide.sensibull.com/v1/compute/cache/instrument_metacache/2"
    resp_api = session.get(api_url)
    resp_api.raise_for_status()

    data = resp_api.json()
    options = []
    derivatives = data['derivatives']
    for script in derivatives:
        for exp in derivatives[script]['derivatives']:
            expiry = derivatives[script]['derivatives'][exp]
            if 'options' in expiry:
                opts = expiry['options']
                for strike in opts:
                    try:
                        float(strike)
                    except:
                        continue
                    for opt_type in opts[strike]:
                        opt = opts[strike][opt_type]
                        opt['strike'] = strike
                        opt['expiry'] = exp
                        opt['underlying'] = script
                        opt['option_type'] = opt_type
                        if 'segment' in opt:
                            del opt['segment']
                        if 'exchange' in opt:
                            del opt['exchange']
                        if 'tick_size' in opt:
                            del opt['tick_size']
                        if 'lot_size' in opt:
                            del opt['lot_size']
                        options.append(opt)
    return pd.DataFrame(options)

def get_futures():
    import requests 
    session = requests.Session()
    api_url = "https://oxide.sensibull.com/v1/compute/cache/instrument_metacache/2"
    resp_api = session.get(api_url)
    resp_api.raise_for_status()

    data = resp_api.json()
    futures = []
    derivatives = data['derivatives']
    for script in derivatives:
        for exp in derivatives[script]['derivatives']:
            expiry = derivatives[script]['derivatives'][exp]
            if 'FUT' in expiry:
                fut = expiry['FUT']
                fut['expiry'] = exp
                fut['underlying'] = script
                fut['expiry_type'] = 'monthly'
                fut['option_type'] = 'FUT'
                fut['strike'] = -1
                if 'segment' in fut:
                    del fut['segment']
                if 'exchange' in fut:
                    del fut['exchange']
                if 'tick_size' in fut:
                    del fut['tick_size']
                if 'lot_size' in fut:
                    del fut['lot_size']
                futures.append(fut)
    return pd.DataFrame(futures)

def get_fno():
    import requests 
    session = requests.Session()
    api_url = "https://oxide.sensibull.com/v1/compute/cache/instrument_metacache/2"
    resp_api = session.get(api_url)
    resp_api.raise_for_status()

    data = resp_api.json()
    nse_eq = data['underlyer_list']['NSE']['NSE']['EQ']
    fno = []
    for script in nse_eq:
        d = nse_eq[script]
        if 'closest_future' in d:
            del d['closest_future']
        if 'sectors' in d:
            del d['sectors']
        if 'segment' in d:
            del d['segment']
        d['underlying'] = script
        fno.append(d)
    nse_indices = data['underlyer_list']['NSE']['NSE-INDICES']['EQ']
    for script in nse_indices:
        d = nse_indices[script]
        if 'closest_future' in d:
            del d['closest_future']
        if 'sectors' in d:
            del d['sectors']
        if 'segment' in d:
            del d['segment']
        d['underlying'] = script
        fno.append(d)
    return pd.DataFrame(fno)

class DB:
    def __init__(self, db_file):
        self.conn = sqlite3.connect(db_file)
        self.cursor = self.conn.cursor()
        self._create_tables()
        
    def _create_tables(self):
        # scripts table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS scripts (
                instrument_token INTEGER PRIMARY KEY,
                is_non_fno BOOLEAN,
                name TEXT,
                tradingsymbol TEXT UNIQUE,
                tick_size REAL,
                underlying TEXT,
                lot_size REAL
            )
        """)
        
        # iv table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS iv (
                script TEXT,
                date TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                iv REAL,
                UNIQUE(script, date)
            )
        """)    

        # fno_scripts table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS fno_scripts (
                instrument_token INTEGER PRIMARY KEY,
                tradingsymbol TEXT UNIQUE,
                underlying TEXT,
                expiry TEXT,
                expiry_type TEXT,
                option_type TEXT,
                strike REAL,
                UNIQUE(underlying, expiry, expiry_type, option_type, strike)
            )
        """)
        # --- indexes for faster queries ---
        # scripts lookups
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_scripts_tradingsymbol ON scripts(tradingsymbol)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_scripts_underlying ON scripts(underlying)")

        # iv queries by symbol + date range
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_iv_symbol_date ON iv(script, date)")

        # fno_scripts queries (common filters: underlying + expiry + strike + option_type)
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_fno_underlying_expiry ON fno_scripts(underlying, expiry)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_fno_symbol ON fno_scripts(tradingsymbol)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_fno_option_strike ON fno_scripts(option_type, strike)")


        self.conn.commit()

    def _insert_dataframe(self, df: pd.DataFrame, table: str, mode: str = "replace"):
        """
        Insert rows from a pandas DataFrame into the given table.
        Args:
            df (pd.DataFrame): dataframe with columns matching the table
            table (str): table name
            mode (str): "replace" (INSERT OR REPLACE) or "ignore" (INSERT OR IGNORE)
        """
        if df.empty:
            return

        cols = ",".join(df.columns)
        placeholders = ",".join("?" * len(df.columns))

        if mode == "ignore":
            sql = f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({placeholders})"
        else:
            sql = f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({placeholders})"

        records = [tuple(x) for x in df.to_numpy()]
        self.cursor.executemany(sql, records)
        self.conn.commit()

    
    
    def insert_futures(self, futures: pd.DataFrame):
        self._insert_dataframe(futures, "fno_scripts")
    
    def insert_options(self, options: pd.DataFrame):
        self._insert_dataframe(options, "fno_scripts")
    
    def insert_iv(self, iv: pd.DataFrame):
        self._insert_dataframe(iv, "iv")
    
    def insert_fno_scripts(self, fno_scripts: pd.DataFrame):
        self._insert_dataframe(fno_scripts, "scripts")


if __name__ == "__main__":
    db = DB(SQLITE_DB_FILE)
    futures = get_futures()
    db.insert_futures(futures)
    options = get_options()
    db.insert_options(options)
    fno_scripts = get_fno()
    db.insert_fno_scripts(fno_scripts)
    scripts = fno_scripts['tradingsymbol'].unique().tolist()
    pbar = tqdm(scripts)
    failures = 0
    successes = 0
    with open("download_errors.txt", "w", encoding="utf-8") as f:
        for script in pbar:
            pbar.set_description(f"Downloading IV for {script}")
            pbar.set_postfix(successes=successes,failed=failures)
            try:
                iv = get_io(script)
                db.insert_iv(iv)
                successes += 1
            except Exception as e:
                f.write(f"{script}: {e}\n")
                failures += 1
            pbar.set_postfix(successes=successes,failed=failures)
    print(f"Total failures: {failures}")
    


    
    