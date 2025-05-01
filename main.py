# every hour run the following loop


# centroids.py 
#       to refresh our centroids

# ranking.py 
#       to get the "bin probability score" for the current day and rank the coins by score

# orders.py
#       to filter the good times to trade by the bad times to trade (bin score cut off at 90%)
#       to allocate USDT on the book side to those good potential trades

# buyer.py
#       to take the orders then create and submit buy orders to kraken via API

# seller.py
#       to monitor pending orders, when filled then submit the stop loss order
