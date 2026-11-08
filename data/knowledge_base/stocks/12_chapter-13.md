---
title: "Chapter 13"
category: "stocks"
source: "Zerodha Varsity"
module: "Technical Analysis"
tags:
  - "equity"
  - "stocks"
---

## Chapter 13

Moving Averages
We have all learnt about averages in school, moving average is just an extension of
that. Moving averages are trend indicators and are frequently used due to their
simplicity and effectiveness. Before we learn moving averages, let us have a quick
recap on how averages are calculated.
Assume 5 people are sitting on a nice sunny beach enjoying a nice chilled bottled
beverage. The sun is so bright and nice that each one of them end up drinking
several bottles of the beverage. Assume the final count to be something like this:
Sl No Person No of Bottles
01 A 07
02 B 05
03 C 06
04 D 03
05 E 08
Total # of bottles consumed 29
Assume a 6th person walks in to find out 29 bottles of beverages lying around them.
He can quickly get a sense of ‘roughly’ how many bottles each of them consumed by
dividing [the total number of bottles] by [total number of people].
In this case it would be:
=29/5
=5.8 bottles per head.
So, the average in this case tells us roughly how many bottles each person had
consumed. Obviously there would be few of them who had consumed above and
below the average. For example, Person E drank 8 bottles of beverage, which is way
above the average of 5.8 bottles. Likewise, person D drank just 3 bottles of
beverage, which is way below the average of 5.8 bottles. Therefore average is just
an estimate and one cannot expect it to be accurate.
Extending the concept to stocks, here are the closing prices of ITC Limited for the
last 5 trading sessions. The last 5 day average close would be calculated as follows:
Date Closing Price
14/07/14 344.95
15/07/14 342.35
16/07/14 344.20
17/07/14 344.25
18/07/14 344.0
Total 1179.75
= 1179.75 / 5
= 343.95
Hence the average closing price of ITC over the last 5 trading sessions is 343.95.
13.1 – The ‘moving’ average (also called the simple moving average)
Consider a situation where you want to calculate the average closing price of Marico
Limited for the latest5 days. The data is as follows:
Date Closing Price
21/07/14 239.2
22/07/14 240.6
23/07/14 241.8
24/07/14 242.8
25/07/14 247.9
Total 1212.3
= 1212.3/ 5
= 242.5
Hence the average closing price of Marico over the last 5 trading sessions is 242.5
Moving forward, the next day i.e 28th July (26th and 27th were Saturday and Sunday
respectively) we have a new data point. This implies now the ‘new’ latest 5 days
would be 22nd, 23rd, 24th, 25th and 28th. We will drop the data point belonging to the
21st as our objective is to calculate the latest 5 day average.
Date Closing Price
22/07/14 240.6
23/07/14 241.8
24/07/14 242.8
25/07/14 247.9
28/07/14 250.2
Total 1223.3
= 1223.3/ 5
= 244.66
Hence the average closing price of Marico over the last 5 trading sessions is 244.66
As you can see, we have included the latest data (28th July), and discarded the oldest
data (21st July) to calculate the 5 day average. On 29th, we would include 29th data
and exclude 22nd data, on 30th we would include 30th data point but eliminate
23rd data, so on and so forth.
So essentially, we are moving to the latest data point and discarding the oldest to
calculate the latest 5 day average. Hence the name “moving” average!
In the above example, the calculation of moving average is based on the closing
prices. Sometimes, moving averages are also calculated using other parameters
such as high, low, and open. However the closing prices are used mostly by the
traders and investors as it reflects the price at which the market finally settles down.
Moving averages can be calculated for any time frame, from minutes, hours to
years. Any time frame can be selected from the charting software based of your
requirements.
For those of you familiar with excel, here is a screenshot of how moving averages
are calculated on MS Excel. Notice how the cell reference moves in the average
formula, eliminating the oldest to include the latest data points.
Cell Ref Date Close Price 5 Day Average Average Formula
D3 1-Jan-14 1287.7
D4 2-Jan-14 1279.25
D5 3-Jan-14 1258.95
D6 6-Jan-14 1249.7
D7 7-Jan-14 1242.4
D8 8-Jan-14 1268.75 1263.6 =AVERAGE(D3:D7)
D9 9-Jan-14 1231.2 1259.81 =AVERAGE(D4:D8)
D10 10-Jan-14 1201.75 1250.2 =AVERAGE(D5:D9)
D11 13-Jan-14 1159.2 1238.76 =AVERAGE(D6:D10)
D12 14-Jan-14 1157.25 1220.66 =AVERAGE(D7:D11)
D13 15-Jan-14 1141.35 1203.63 =AVERAGE(D8:D12)
D14 16-Jan-14 1152.5 1178.15 =AVERAGE(D9:D13)
D15 17-Jan-14 1139.6 1162.41 =AVERAGE(D10:D14)
D16 20-Jan-14 1140.6 1149.98 =AVERAGE(D11:D15)
D17 21-Jan-14 1166.35 1146.26 =AVERAGE(D12:D16)
D18 22-Jan-14 1165.4 1148.08 =AVERAGE(D13:D17)
D19 23-Jan-14 1168.25 1152.89 =AVERAGE(D14:D18)
As it is evident, the moving average changes as and when the closing price changes.
A moving average as calculated above is called a ‘Simple Moving Average’ (SMA).
Since we are calculating it as per the latest 5 days of data it is called referred to as 5
Day SMA.
The averages for the 5 day (or it could be anything like 5, 10, 50, 100, 200 days) are
then joined to form a smooth curving line known as the moving average line, and it
continues to move as the time progresses.
In the chart shown below, I have overlaid a 5 day SMA over ACC’s candlestick graph.
So what does a moving average indicate and how does one use it? Well, there are
many applications of moving average and shortly I will introduce a simple trading
system based on moving averages. But before that, let us learn about the
Exponential Moving Average.
13.2 – The exponential moving average
Consider the data points used in the this example,
Date Closing Price
22/07/14 240.6
23/07/14 241.8
24/07/14 242.8
25/07/14 247.9
28/07/14 250.2
Total 1214.5
When one calculates the average across these numbers there is an unstated
assumption. We are essentially giving each data point equal importance. Meaning,
we are assuming that the data point on 22ndJuly is as important as the data point on
28th July. However, when it comes to markets, this may not always be true
Remember the basic assumption of technical analysis – markets discount
everything. This means the latest price that you see (on 28th July) discounts all the
known and unknown information. This also implies the price on 28th is more sacred
than the price on 25th.
Going by this, one would like to assign weightage to data points based on the
‘newness’ of the data. Therefore the data point on 28th July gets the highest
weightage, 25th July gets the next highest weightage, 24th July gets the 3rd highest, and
so on.
By doing so, I have essentially scaled the data points according to its newness – the
latest data point gets the maximum attention and the oldest data point gets the
least attention.
The average calculated on this scaled set of numbers gives us the Exponential
Moving Average (EMA). I deliberately skipped the EMA calculation part, simply
because most of the technical analysis software lets us drag and drop the EMA on
prices. Hence we will focus on EMA’s application as opposed to its calculation.
Here is a chart of Cipla Ltd. I have plotted a 50 day SMA (black) and a 50 day EMA
(red) on Cipla’s closing prices. Though both SMA and EMA are for a 50 day period,
you can notice that the EMA is more reactive to the prices and hence it sticks closer
to the price.
The reason why EMA is quicker to react to the current market price is because EMA
gives more importance to the most recent data points. This helps the trader to take
quicker trading decisions. Hence for this reason, traders prefer the use of the EMA
over the SMA.
13.3 – A simple application of moving average
The moving average can be used to identify buying and selling opportunities with its
own merit. When the stock price trades above its average price, it means the traders
are willing to buy the stock at a price higher than its average price. This means the
traders are optimistic about the stock price going higher. Therefore one should look
at buying opportunities.
Likewise, when the stock price trades below its average price, it means the traders
are willing to sell the stock at a price lesser than its average price. This means the
traders are pessimistic about the stock price movement. Therefore one should look
at selling opportunities.
We can develop a simple trading system based on these conclusions. A trading
system can be defined as a set of rules that help you identify entry and exit points.
We will now try and define one such trading system based on a 50 day exponential
moving average. Remember a good trading system gives you a signal to enter a
trade and a signal to close out the trade. We can define the moving average trading
system with the following rules:
Rule 1) Buy (go long) when the current market price turns greater than the 50 day
EMA. Once you go long, you should stay invested till the necessary sell condition is
satisfied
Rule 2) Exit the long position (square off) when the current market price turns lesser
than the 50 day EMA
Here is a chart that shows the application of the trading system on Ambuja
cements. The black line on the price chart is the 50 day exponential moving average.
Starting from left, the first opportunity to buy originated at 165, highlighted on the
charts as B1@165. Notice, at point B1, the stock price moved to a point higher than
its 50 day EMA. Hence as per the trading system rule, we initiate a fresh long
position.
Going by the trading system, we stay invested till we get an exit signal, which we
eventually got at 187, marked as S1@187. This trade generated a profit of Rs.22 per
share.
The next signal to go long came at B2@178, followed by a signal to square off
at S2@182. This trade was not impressive as it resulted in a profit of just Rs.4.
However the last trade, B3@165, and S3@215 was quite impressive resulting in a
profit of Rs.50.
Here is a quick summary of these trades based on the trading system fared:
Sl No Buy Price Sell Price Gain/Loss % Return
01 165 187 22 13%
02 178 182 04 2.2%
03 165 215 50 30%
From the above table, it is very clear that the first and last trades were profitable,
but the 2nd trade was not so profitable. If you inspect why this happened, it is
evident that during the 1st and the 3rd trade, the stock was trending but during the
2nd trade the stock moved sideways.
This leads us to a very important conclusion about the moving averages. Moving
averages works brilliantly when there is a trend and fails to perform when the stock
moves sideways. This basically means the ‘Moving average’ in its simplest form is a
trend following system.
From my own personal experience of trading based on moving averages, I have
noticed a few important characteristics:
1. Moving averages gives you many trading signals (buy and sell) during a sideways
market. Most of these signals result in marginal profits, if not for losses
2. However usually one of those many trades results in a massive rally (like
the B3@165 trade) leading to impressive gains
3. It would be very difficult to segregate the big winner from the many small trades
4. Hence the trader should not be selective in terms of selecting signals that moving
average system suggest. In fact the trader should trade all the trades that the
system suggests
5. Remember the losses are minimum in a moving average system, but that 1 big
trade is good enough to compensate all the losses and can give you sufficient
profits
6. The profit making trade ensures you are in the trend as long as the trend lasts.
Sometime even upto several months. For this reason, MA can be used as a proxy for
identifying long term investment ideas
7. The key to MA trading system is to take all the trades and not be judgmental about
the signals being generated by the system.
Here is another example of BPLC, where the MA system suggested multiple trades
during the sideways market, however none of them were really profitable. However,
the last trade resulted in a 67% profit in about 5 months.
13.4 – Moving average crossover system
As its evident now the problem with the plain vanilla moving average system is that
it generates far too many trading signals in a sideway market. A moving average
crossover system is an improvisation over the plain vanilla moving average system.
It helps the trader to take fewer trades in a sideways market.
In a MA crossover system, instead of the usual single moving average, the trader
combines two moving averages. This is usually referred to as ‘smoothing’.
A typical example of this would be to combine a 50 day EMA, with a 100 day EMA.
The shorter moving average (50 days in this case) is also referred to as the faster
moving average. The longer moving average (100 days moving average) is referred
to as the slower moving average.
The shorter moving average takes lesser number of data points to calculate the
average and hence it tends to stick closer to the current market price, and therefore
reacts more quickly. A longer moving average takes more number of data points to
calculate the average and hence it tends to stay away from the current market price.
Hence the reactions are slower.
Here is the chart of Bank of Baroda, showing you how the two moving averages
stack up when loaded on a chart.
As you can see, the black 50 day EMA line is closer to the current market price (as it
reacts faster) when compared to the pink 100 day EMA (as its reacts slower).
Traders have modified the plain vanilla MA system with the crossover system to
smoothen out the entry and exit points. In the process, the trader gets far fewer
signals, but the chances of the trade being profitable are quite high.
The entry and exit rules for the crossover system is as stated below:
Rule 1) – Buy (fresh long) when the short term moving averages turns greater than
the long term moving average. Stay in the trade as long as this condition is satisfied
Rule 2) – Exit the long position (square off) when the short term moving average
turns lesser than the longer term moving average
Let us apply the MA crossover system to the same BPCL example that we looked at.
For ease of comparison, I have reproduced the BPCL’s chart with a single 50 day MA.
Notice, when the markets were moving sideways, MA suggested at least 3 trading
signals. However the 4thtrade was the winner which resulted in 67% profit.
The chart shown below shows the application of a MA crossover system with 50 and
100 day EMA.
The black line plots the 50 day moving average and the pink line plots the 100 day
moving average. As per the cross over rule, the signal to go long originates when the
50 day moving average (short term MA) crosses over the 100 day moving average
(long term MA). The crossover point has been highlighted with an arrow. Please do
notice how the crossover system keeps the trader away from the 3 unprofitable
trades. This is the biggest advantage of a cross over system.
A trader can use any combination to create a MA cross over system. Some of the
popular combinations for a swing trader would be:
1. 9 day EMA with 21 day EMA – use this for short term trades ( upto few trading
session)
2. 25 day EMA with 50 day EMA – use this to identify medium term trade (upto few
weeks)
3. 50 day EMA with 100 Day EMA – use this to identify trades that lasts upto few
months
4. 100 day EMA with 200 day EMA – use this to identify long term trades (investment
opportunities), some of them can even last for over a year or more.
Remember, longer the time frame the lesser the number of trading signals.
Here is an example of a 25 x 50 EMA crossover. There are three trading signals that
qualify under the crossover rule.
Needless to say, the MA crossover system can also be applied for intraday trading.
For instance one could use the 15 x 30 minutes crossover to identify intraday
opportunities. A more aggressive trader could use 5 x 10 minute crossover.
You may have heard this popular saying in the markets – “The trend is you friend”.
Well, the moving averages help you identify this friend.
Remember, MA is a trend following system – as long as there is a trend, the moving
averages works brilliantly. It does not matter which time frame you use or which
cross over combination you use.
Key takeaways from this chapter
1. A standard average calculation is a quick approximation of a series of numbers
2. In a average calculation where the latest data is included, and the oldest is excluded
is called a Moving Average
3. The simple moving average (SMA) gives equal weightage to all data points in the
series
4. An exponential moving average (EMA) scales the data according to its newness.
Recent data gets the maximum weightage and the oldest gets the least weightage
5. For all practical purposes, use an EMA as opposed to SMA. This is because the EMA
gives more weightage to the most recent data points
6. The outlook is bullish when the current market price is greater than the EMA. The
outlook turns bearish when the current market price turns lesser than the EMA
7. In a non trending market, moving averages may result in whipsaws thereby causing
frequent losses. To overcome this a EMA crossover system is adopted
8. In a typical crossover system, the price chart is over laid with two EMAs. The shorter
EMA is faster to react, while the longer EMA is slower to react
9. The outlook turns bullish when the faster EMA crosses and is above the slower EMA.
Hence one should look at buying the stock. The trade lasts upto a point where the
faster EMA starts going below the slower EMA
10. The longer the time frame one chooses for a crossover system, the lesser the
trading signals.
Module 2 — Technical Analysis
