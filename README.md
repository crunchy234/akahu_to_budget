# akahu_to_budget
One-way sync of transactions from Akahu to either YNAB or Actual Budget.

We support both Actual Budget and YNAB.  You can sync to both or to just one.

# Project status

I started writing this script some time ago. As of 2024-12-28... I've finally swapped from using my old hodgepodge version to using this.
That means that today, it's feature complete but not yet battle-hardened.  If you're reading this notably after Dec 2024 then it should be pretty robust.

Also in terms of my personal setup, I haven't yet fully committed to giving up YNAB and an vascilating between YNAB and AB.  You might see oddities in the data 
created for AB (e.g. Payees, failing to trigger rules).  Please raise bugs.

# Setup

1. Create an Akahu account and an Akahu app: [https://my.akahu.nz/login](https://my.akahu.nz/login)
2. Set up an OpenAI account and get an API key: [https://platform.openai.com/account/api-keys](https://platform.openai.com/account/api-keys) (OPTIONAL)
3. Set up an Actual Budget Server and get the server URL, password, encryption key, and sync ID: [https://actualbudget.org/](https://actualbudget.org/).  I used PikaPods
4. And/OR in YNAB get a bearer token and the budget ID: [https://api.youneedabudget.com/](https://api.youneedabudget.com/)
5. Check out this repository
6. Create a virtual environment and run `pip install -r requirements.txt`
7. Create a `.env` file in the root of the project with the following variables:
```
AKAHU_API_KEY=<your_akahu_api_key>
AKAHU_API_SECRET=<your_akahu_api_secret>
ACTUAL_SERVER_URL="https://<your actual budget host>/"
ACTUAL_PASSWORD="your actual budget password"
ACTUAL_ENCRYPTION_KEY="your actual budget encryption key"
ACTUAL_SYNC_ID="the Sync ID of the budget you want to sync"
AKAHU_APP_TOKEN="your akahu app token"
AKAHU_PUBLIC_KEY="Reserved for Future Use"
AKAHU_USER_TOKEN="your akahu user token"
FLASK_ENV="development"
OPENAI_API_KEY="your openai key"
YNAB_BEARER_TOKEN="your ynab bearer token"
YNAB_BUDGET_ID="The budget you want to sync"
```
Note that the OPENAI key is optional.  I included it more for fun.  It makes the matching a bit smarter

# Preparing to run the script

Run `python akahu_budget_mapping.py`

This will ask you a bunch of questions like 
```Akahu Account: DAY TO DAY (Connection: Kiwibank)
Here is a list of target accounts:
...
Enter the number corresponding to the best match (or press Enter to skip):
```

Ultimately this will write the file `akahu_budget_mapping.json`.

You will likely never need to run this again unless you want to change the mapping.

# Running the script

Now run `akahu_to_budget.py`

This is the workhorse.  It connects to Akahu, gets the transactions, and then syncs them to Actual Budget and/or YNAB.

It's implemented as a Flask app so you can run it locally and it will keep running.  
The first sync is triggered automatically on startup.  For subsequent syncs you should use the web interface.
There is minimal security, mostly because the webhooks don't take parameters so the worst someone can do is sync your budget prematurely.

You can run the sync by going to http://localhost:5000/sync

# Running Tests

There are some tests to validate the API is still working.  You can probably ignore them.

# OpenAI

I set up the OpenAI key for mapping accounts more out of self-amusement.  I have also toyed with the idea of using it to clean payees, assign transactions to categories, etc.
For now it's not really doing anything.