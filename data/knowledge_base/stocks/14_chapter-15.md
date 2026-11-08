---
title: "Chapter 15"
category: "stocks"
source: "Zerodha Varsity"
module: "Technical Analysis"
tags:
  - "equity"
  - "index"
  - "nifty"
  - "risk"
  - "stocks"
  - "volatility"
---

## Chapter 15

Indicators (Part 2)
15.1 Moving Average Convergence and Divergence (MACD)
The Moving Average Convergence and Divergence (MACD) indicator was developed
by Gerald Appel in the late seventies. Traders consider MACD as the grand old
daddy of indicators. Though invented in the seventies, MACD is still considered as
one of the most reliable indicators by momentum traders.
As the name suggests, MACD is all about the convergence and divergence of the two
moving averages. Convergence occurs when the two moving averages move
towards each other, and a divergence occurs when the moving averages move away
from each other.
A standard MACD is calculated using a 12 day EMA and a 26 day EMA. Please note,
both the EMA’s are based on the closing prices.We subtract the 26 EMA from the 12
day EMA, to estimate the convergence and divergence (CD) value. A simple line
graph of this is often referred to as the ‘MACD Line’. Let us go through the math
first and then figure out the applications of MACD.
Date Close 12 Day EMA 26 Day EMA MACD Line
1-Jan-14 6302
2-Jan-14 6221
3-Jan-14 6211
6-Jan-14 6191
7-Jan-14 6162
8-Jan-14 6175
9-Jan-14 6168
10-Jan-14 6171
13-Jan-14 6273
14-Jan-14 6242
15-Jan-14 6321
16-Jan-14 6319
17-Jan-14 6262 6230
20-Jan-14 6304 6226
21-Jan-14 6314 6233
22-Jan-14 6339 6242
23-Jan-14 6346 6254
24-Jan-14 6267 6269
27-Jan-14 6136 6277
28-Jan-14 6126 6274
29-Jan-14 6120 6271
30-Jan-14 6074 6258
31-Jan-14 6090 6244
3-Feb-14 6002 6225
4-Feb-14 6001 6198
5-Feb-14 6022 6176
6-Feb-14 6036 6153 6198 -45
7-Feb-14 6063 6130 6188 -58
10-Feb-14 6053 6107 6182 -75
11-Feb-14 6063 6083 6176 -94
12-Feb-14 6084 6066 6171 -106
13-Feb-14 6001 6061 6168 -107
Let us go through the table starting from left:
1. We have the dates, starting from 1st Jan 2014
2. Next to the dates we have the closing price of Nifty
3. We leave the first 12 data points (closing price of Nifty) to calculate the 12 day EMA
4. We then leave the first 26 data points to calculate the 26 day EMA
5. Once we have both 12 and 26 day EMA running parallel to each other (6th Feb 2014)
we calculate the MACD value
6. MACD value = [12 day EMA – 26 day EMA]. For example on 6th Feb 2014, 12 day EMA
was 6153, and 26 day EMA was 6198, hence the MACD would be 6153-6198 = – 45
When we calculate the MACD value over a series of 12 and 26 day EMAs and plot it
as a line graph, we get the MACD line, which oscillates above and below the central
line.
Date Close 12 Day EMA 26 Day EMA MACD Line
1-Jan-14 6302
2-Jan-14 6221
3-Jan-14 6211
6-Jan-14 6191
7-Jan-14 6162
8-Jan-14 6175
9-Jan-14 6168
10-Jan-14 6171
13-Jan-14 6273
14-Jan-14 6242
15-Jan-14 6321
16-Jan-14 6319
17-Jan-14 6262 6230
20-Jan-14 6304 6226
21-Jan-14 6314 6233
22-Jan-14 6339 6242
23-Jan-14 6346 6254
24-Jan-14 6267 6269
27-Jan-14 6136 6277
28-Jan-14 6126 6274
29-Jan-14 6120 6271
30-Jan-14 6074 6258
31-Jan-14 6090 6244
3-Feb-14 6002 6225
4-Feb-14 6001 6198
5-Feb-14 6022 6176
6-Feb-14 6036 6153 6198 -45
7-Feb-14 6063 6130 6188 -58
10-Feb-14 6053 6107 6182 -75
11-Feb-14 6063 6083 6176 -94
12-Feb-14 6084 6066 6171 -106
13-Feb-14 6001 6061 6168 -107
14-Feb-14 6048 6051 6161 -111
17-Feb-14 6073 6045 6157 -112
18-Feb-14 6127 6045 6153 -108
19-Feb-14 6153 6048 6147 -100
20-Feb-14 6091 6060 6144 -84
21-Feb-14 6155 6068 6135 -67
24-Feb-14 6186 6079 6129 -50
25-Feb-14 6200 6092 6126 -34
26-Feb-14 6239 6103 6122 -19
28-Feb-14 6277 6118 6119 -1
3-Mar-14 6221 6136 6117 20
4-Mar-14 6298 6148 6112 36
5-Mar-14 6329 6172 6113 59
6-Mar-14 6401 6196 6121 75
7-Mar-14 6527 6223 6131 92
10-Mar-14 6537 6256 6147 110
11-Mar-14 6512 6288 6165 124
12-Mar-14 6517 6324 6181 143
13-Mar-14 6493 6354 6201 153
14-Mar-14 6504 6380 6220 160
Given the MACD value, lets try and find the answer for few obvious questions:
1. What does a negative MACD value indicate?
2. What does a positive MACD value indicate?
3. What does the magnitude of the MACD value actually mean? As in, what information
does a -90 MACD convey versus a – 30 MACD ?
The sign associated with the MACD just indicates the direction of the stock’s move.
For example if the 12 Day EMA is 6380, and 26 Day EMA is 6220 then the MACD
value is +160. Now, under what circumstance do you think the 12 day EMA will be
greater than the 26 day EMA? Well, we had looked into this in the moving average
chapter. The shorter term average will generally be higher than the longer term only
when the stock price is trending upwards. Also, do remember, the shorter term
average will always be more reactive to the current market price than the longer
term average. Hence a positive sign tells us that there is positive momentum in the
stock, and the stock is drifting upwards. The higher the momentum, the higher is
the magnitude. For example, +160 indicate a positive trend which is stronger than
+120.
However, while dealing with the magnitude, always remember the price of the stock
influences the magnitude. For example, higher the underlying price such as Bank
Nifty, naturally, the higher will be the magnitude of the MACD.
When the MACD is negative, it means the 12 day EMA is lower than the 26 day EMA.
Therefore the momentum is negative. Higher the magnitude of the MACD, the more
strength in the downward trend.
The difference between the two moving averages is called the MACD spread. The
spread decreases when the momentum mellows down and increases when the
momentum increases. To visualize convergence and the divergence traders usually
plot the chart of the MACD value, often referred to as the MACD line.
The following is the MACD line chart of Nifty for data points starting from 1st Jan
2014 to 18th Aug 2014.
As you can see the MACD line oscillates over a central zero line. This is also called
the ‘Center line’. The basic interpretation of the MACD indicator is that:
1. When the MACD Line crosses the center line from the negative territory to positive
territory, it means there is divergence between the two averages. This is a sign of
increasing bullish momentum; therefore one should look at buying opportunities.
From the chart above, we can see this panning out around 27thFeb
2. When the MACD line crosses the center line from positive territory to the negative
territory it means there is convergence between the two averages. This is a sign of
increasing bearish momentum; therefore one should look at selling opportunities.
As you can see, there were two instance during which the MACD almost turned
negative (8th May, and 24th July) but the MACD just stopped at the zero line and
reversed directions
Traders generally argue that while waiting for the MACD line to crossover the center
line a bulk of the move would already be done and perhaps it would be late to enter
a trade. To overcome this, there is an improvisation over this basic MACD line. The
improvisation comes in the form of an additional MACD component which is the 9
day signal line. A 9 day signal line is a exponential moving average (EMA) of the
MACD line. If you think about this, we now have two lines:
1. A MACD line
2. A 9 day EMA of the MACD line, also called the signal line
With these two lines, a trader can follow a simple 2 line crossover strategy as
discussed in the moving averages chapter, and no longer wait for the center line
cross over.
1. The sentiment is bullish when the MACD line crosses the 9 day EMA wherein MACD
line is greater than the 9 day EMA. When this happens, the trader should look at
buying opportunities
2. The sentiment is bearish when the MACD line crosses below the 9 day EMA wherein
the MACD line is lesser than the 9 day EMA. When this happens, the trader should
look at selling opportunities
The chart below plots the MACD indicator on Asian Paints Limited. You can see the
MACD indicator below the price chart.
The indicator uses standard parameters of MACD:
1. 12 day EMA of closing prices
2. 26 day EMA of closing prices
3. MACD line (12D EMA – 26D EMA) represented by the black line
4. 9 day EMA of the MACD line represented by the red line
The vertical lines on the chart highlight the crossover points on the chart where a
signal to either buy or sell has originated.
For example, the first vertical line starting from left points to a crossover where the
MACD line lies below the signal line (9 day EMA) lies and suggests a short trade.
The 2nd vertical line from left, points to a crossover where the MACD line lies above
the signal line, hence one should look at buying opportunity. So on and so forth.
Please note, at the core of the MACD system, are moving averages. Hence the MACD
indicator has similar properties like that of a moving average system. They work
quite well when there is a strong trend and are not too useful when the markets are
moving sideways. You can notice this between the 1st two line starting from left.
Needless to say, the MACD parameters are not set in stone. One is free to change
the 12 day, and 26 day EMA to whatever time frame one prefers. I personally like to
use the MACD in its original form, as introduced by Gerald Appel.
15.2 – The Bollinger Bands
Introduced by John Bollinger in the 1980s, Bollinger bands (BB) is perhaps one of
the most useful indicators used in technical analysis. BB are used to determine
overbought and oversold levels, where a trader will try to sell when the price
reaches the top of the band and will execute a buy when the price reaches the
bottom of the band.
The BB has 3 components:
1. Middle line which is The 20 day simple moving average of the closing prices
2. An upper band – this is the +2 standard deviation of the middle line
3. A lower band – this is the -2 standard deviation of the middle line
The standard deviation (SD) is a statistical concept; which measures the variance of
a particular variable from its average. In finance, the standard deviation of the stock
price represents the volatility of a stock. For example, if the standard deviation of a
stock is 12%, it is as good as saying that the volatility of the stock is 12%.
In BB, the standard deviation is applied on the 20 day SMA. The upper band
indicates the +2 SD. By using a +2 SD, we simply multiply the SD by 2, and add it to
the average.
For example if the 20 day SMA is 7800, and the SD is 75 (or 0.96%), then the +2 SD
would be 7800 + (75*2) = 7950. Likewise, a -2 SD indicates we multiply the SD by 2,
and subtract it from the average. 7800 – (2*75) = 7650.
We now have the components of the BB:
1. 20 day SMA = 7800
2. Upper band = 7950
3. Lower band = 7650
Statistically speaking, the current market price should hover around the average
price of 7800. However, if the current market price is around 7950, then it is
considered expensive with respect to the average, hence one should look at
shorting opportunities with an expectation that the price will scale back to its
average price.
Therefore the trade would be to sell at 7950, with a target of 7800.
Likewise if the current market price is around 7650, it is considered cheap with
respect to the average prices, and hence one should look at buying opportunities
with and expectation that the prices will scale back to its average price.
Therefore the trade would be to buy at 7650, with a target of 7800.
The upper and lower bands act as a trigger to initiate a trade.
The following is the chart of BPCL Limited,
The central black line is the 20 day SMA. The two red lines placed above and below
the black like are the +2 SD, and -2SD. The idea is to short the stock when the price
touches the upper band with an expectation that it will revert to average. Likewise
one can go long when the price touches the lower band with an expectation it will
revert to the average.
I have highlighted using a down arrow all the sell signals BB generated, while most
of the signals worked quite well, there was a phase when the price stuck to the
upper band. In fact the price continued to drift higher, and therefore even the upper
band expanded. This is called an envelope expansion.
The BB’s upper and lower band together forms an envelope. The envelope expands,
whenever the price drifts in a particular direction indicating a strong momentum.
The BB signal fails when there is an envelope expansion. This leads us to an
important conclusion; BB works well in sideways markets, and fails in a trending
market.
Personally whenever, I use BB I expect the trade to start working in my favor almost
immediately. If it does not, I start validating the possibility of an envelope
expansion.
15.3 – Other Indicators
There are numerous other technical indicators, and the list is endless. The question
is, should you know all these indicators to be a successful trader? The answer is a
simple no. Technical indicators are good to know, but they by no means should be
your main tool of analysis.
I have personally met many aspiring traders who spend a lot of time, and energy
learning different indicators, but this in the long run is futile. The working
knowledge of few basic indicators, such as the ones discussed in this module are
sufficient.
15.4 – The Checklist
In the previous chapters, we started building a checklist that acts as a guiding force
behind the trader’s decision to buy or sell. It is time to revisit that checklist.
The indicators act as tool which the traders can use to confirm their trading
decisions, it is worthwhile to check what the indicators are conveying before placing
a buy or a sell order. While the dependence on indicators is not as much S&R,
volumes or candlestick patterns, it is always good to know what the basic indicators
are suggesting. For this reason, I would recommend adding indicators in the
checklist, but with a twist to it. I will explain the twist in a bit, but before that let us
reproduce the updated checklist.
1. The stock should form a recognizable candlestick pattern
2. S&R should confirm to the trade. The stoploss price should be around S&R
1. For a long trade, the low of the pattern should be around the support
2. For a short trade, the high of the pattern should be around the resistance
3. Volumes should confirm
1. Ensure above average volumes on both buy and sell day
2. Low volumes are not encouraging, hence do feel free to hesitate while taking trade
where the volumes are low
4. Indicators should confirm
1. Scale the size higher if the confirm
2. If they don’t confirm, go ahead with the original plan
The sub bullet points under indicators are where the twist lies.
Now, hypothetically imagine a situation where you are looking at opportunity to buy
shares of Karnataka Bank Limited. On a particular day, Karnataka Bank has formed
a bullish hammer, assume everything ticks on the checklist:
1. Bullish hammer is a recognizable candlestick pattern
2. The low of the bullish hammer also coincides with the support
3. The volumes are above average
4. There is also an MACD crossover (signal line turns greater than the MACD line)
With all four checklist points being ticked off I would be very glad to buy Karnataka
Bank. Hence I place an order to buy, let us say for 500 shares.
However, imagine a situation where the first 3 checklist conditions are met but the
4th condition (indicators should confirm) is not satisfied. What do you think I should
do?
I would still go ahead and buy, but instead of 500 shares, I’d probably buy 300
shares.
This should hopefully convey to you how I tend to (and advocate) the use of
indicators.
When Indicators confirm, I increase my bet size, but when Indicators don’t confirm I
still go ahead with my decision to buy, but I scale down my bet size.
However I would not do this with the first three checklist points. For example, if the
low of the bullish hammer does not coincide in and around the support, then I’ll
really reconsider my plan to buy the stock; in fact I may skip the opportunity, and
look for another opportunity.
But I do not treat the indicators with the same conviction. It is always good to know
what indicators convey, but I don’t base my decisions on that. If the indicators
confirm, I increase the bet size, if they don’t, I still go ahead with my original game
plan.
Key takeaways from this chapter
1. A MACD is a trend following system
2. MACD consists of a 12 Day, 26 day EMA
3. MACD line is 12d EMA – 26d EMA
4. Signal line is the 9 day SMA of the MACD line
5. A crossover strategy can be applied between MACD Line, and the signal line
6. The Bollinger band captures the volatility. It has a 20 day average, a +2 SD, and a -2
7. One can short when the current price is at +2SD with an expectation that the price
reverts to the average
8. One can go long when the current price is at -2SD with an expectation that the price
reverts to the average
9. BB works well in a sideways market. In a trending market the BB’s envelope
expands, and generates many false signals
10. Indicators are good to know, but it should not be treated as the single source for
decision making.
Module 2 — Technical Analysis
