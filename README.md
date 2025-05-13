
# neptune

# Kraken Trading Bot + Dashboard

This repository contains a Kraken cryptocurrency trading bot and a local dashboard for monitoring trading activity and portfolio performance.

---

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/CampbellHarris02/neptune.git
cd neptune
```

### 2. Create a .env File
In the root directory, create a file named .env and add your Kraken API credentials:

```env
KRAKEN_API_KEY=<insert kraken api key>
KRAKEN_API_SECRET=<insert kraken api secret>
```
Do not commit your .env file. It should already be listed in .gitignore.


### 3. (Optional) Create a Virtual Environment
To isolate dependencies:

```bash
python -m venv .venv

source .venv/bin/activate   
# On Windows: .venv\Scripts\activate
```


### 4. Install Dependencies
Install required Python packages using:

```bash
pip install -r requirements.txt
```

### 5. Run the Trading Bot
```bash
python main.py
```

### 6. Run the Dashboard
```bash
go run main.go
```
Then open your browser and navigate to:
http://localhost:5000
