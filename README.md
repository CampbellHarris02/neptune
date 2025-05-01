# neptune

main.py
    every hour run the following loop below

centroids.py 
    refresh our centroids

ranking.py 
    rank the coins by its current "bin probability score" from centroids

orders.py
    filter the good times to trade by the bad times to trade (bin score cut off at 90%)
    allocate USDT on the book side to those good potential trades

buyer.py
    take the orders then create and submit buy orders to kraken via API

seller.py
    to monitor pending orders, when filled then submit the stop loss order


