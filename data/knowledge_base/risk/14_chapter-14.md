---
title: "CHAPTER 14"
category: "risk"
source: "Zerodha Varsity"
module: "Risk Management and Trading Psychology"
tags:
  - "equity"
  - "risk"
  - "stocks"
  - "volatility"
---

## CHAPTER 14

Kelly’s Criterion
14.1 – Percentage Risk
Last chapter we looked at three important position sizing techniques, all of them were unique
in their own merit. The three techniques were –
 Unit per fixed amount
 Percentage Margin
 Percentage Volatility
All three methods work differently and when combined with a certain equity estimation
technique, they produce totally different results. Given this, it is really up to you to figure out
the marriage of which position sizing technique with which equity estimation technique
works best for you.
Before I proceed, I thought it is important to discuss another practical position sizing
technique, called the ‘Percentage Risk’, method. I do know quite a few traders who use this
and I myself find this quite simple and intuitive technique to use.
106 zerodha.com/varsity
The percentage risk method, relies upon your own assessment of ‘loss’ that you are willing
to bear for a given trade. This, as you may know is also called the ‘Stop loss’ for the trade.
The stop loss for a trade is the price at which you decide to close the trade and take a hit. The
percentage risk technique controls the position size as a function of risk defined by stop loss.
Let me take the example of a stock futures and explain how this works, in fact, I think this is
a good trade setup –
Here is an intraday chart of Tata Motors, the frequency is 15 mins (14th Sept 2017, around
11:30 AM).
Let me explain why this is a trade worth considering –
Tata Motors is at 393.65, which happens to be a price action zone, considering it tested the
same level, twice in the past. So this makes 393.65, a support price for Tata Motors (on an
intraday basis). Both the times in the past, the price declined of Tata Motors declined when
the stock tested 393.65. Given this, there is a possibility that the price could again test 393.65
and react to bounce back to the price from which it started to decline i.e 400.
107 zerodha.com/varsity
Also, do notice the low volume retracement between 400 to 393.65 – I’ve discussed why I like
trades like these in the Technical Analysis module. If you’ve not read that module, maybe you
should
Considering these factors, a trader could be inclined to go long on Tata Motors Futures at
393.65.
What if the trade heads the other direction? What is the stop loss?
I notice some sort of support at 390/-, hence I’d be happy to set this as stop loss for the trade.
Nothing complicated, as you can see this is a very straightforward setup.
So the trade would be –
Stock: Tata Motors Limited
Trade: Long
Trade Price: 393.65
Target Price: At least 400
Target value 6.35
Stop loss Price: 390
Stop loss value: 3.65
Reward to Risk: 1.7 (which is great for an intraday trade)
Lot size: 1500
Margin Required: 73.5K
Now assume I have a capital of Rs.500,000/-, how many lots of Tata Motors can I buy
considering the margin per lot is Rs.73,500/-?
Technically speaking one can buy up to 6.8 or 6 lots –
500000/73500
=6.8
108 zerodha.com/varsity
However the question is – would you expose your entire capital to this one trade alone? Not
a smart thing to do, if you were to ask me, because if the trade goes wrong, you would be
losing Rs.32,850/- (3.65 * 1500 * 6) on this trade.
In other words, you would lose –
32850/500000
=6.57% of your capital on one trade.
However great a trade set up is, it is not a smart thing to expose so much capital to risk. As a
thumb rule, professional traders do not risk more than 1 to 3% of their capital on any single
trade, and this rule forms the core of the ‘Percentage risk’ position sizing technique.
Given this, let us define the maximum risk per trade as a percentage of overall capital –
maybe 1.5% for now. This means on this trade, the maximum loss I’m willing to bear is
1.5% * 500000
Rs.7,500/-
In other words, I don’t intend to lose more than Rs.7,500/- on any single trade. This is the
maximum loss threshold.
We know the stop loss for this trade is 390, from an entry price of 393.65, the stop loss in
absolute Rupee terms is –
393.65 – 390
= 3.65
The loss per lot is –
3.65 * 1500
= 5475
In the event the stop loss is triggered I would be taking a hit of Rs.5475 per lot.
Now to identify the number of lots I could take for the risk I’m willing to bear, I simply have
to divide the maximum threshold by the loss per trade.
= 7500/5475
109 zerodha.com/varsity
= 1.36
Therefore, on this trade I can go ahead and buy up to 1 lot, which will cost me Rs.73,500/- as
margin deposits.
For the next trade, it is prudent (or rather conservative in a positive way) to reduce the money
blocked from the overall capital and re-work the maximum loss threshold. Let’s do that and
identify the new max loss threshold –
500000 – 73500
= 426,500
1.5% * 426500
= 6397.5
Given this, for the next trade, I will work out the stop loss, multiply that with the lot size and
divide the max risk i.e 6397.5 by loss threshold to identify how many lots I can transact in.
So on and so forth!
By the way, curious to know how the trade panned out? Here you go –
110 zerodha.com/varsity
I like trades like these, when the price does not even approach close to the stop loss J. As I
had pointed out earlier, I did have a great amount of conviction on this trade. This leads me
to the next topic – how do I position size when my conviction on a particular trade is high?
What in such situations I want to expose a slightly higher capital?
Well, say hello to Kelly’s Criterion!
14.2 – Kelly’s Criterion
Kelly’ Criterion has an interesting background. It was proposed by John Kelly in the 50’s who
at that point was working for AT&T’s Bell Laboratories. He in fact, suggested the Kelly’s
Criterion to help the telecom company with long distance telephone noise issues. However,
the same theory was adopted by professional gamblers to identify the optimal bet size. This
soon found its way to the stock markets as well, and there are many professional traders and
investors who use Kelly’s Criterion for bet sizing. Perhaps, this is one of those very few tools
that both traders and investors commonly use.
I still don’t know how the transition from Telecom to stock markets happened – I’m a Telecom
Engineer by qualification (although I know nothing about Telecommunications now) and I’ve
been involved in Stock markets for over 13+ years….but I just can’t wrap my head around
how Kelly’s Criterion made its transition across these two different worlds J
Anyway, the Kelly’s Criterion essentially helps us estimate the optimal bet size (or the fraction
of our trading capital) considering –
 We have a certain information on the bet we are about to take
 We have an edge taking that particular bet
Let’s jump straight to Kelly’s Criterion with an example. The Kelly’s Criterion is an equation,
the output of which is a percentage, also known as a the Kelly’s percent. The equation is as
below –
Kelly % = W – [(1-W)/R]
Where,
W = Winning probability
R = Win/Loss ratio.
111 zerodha.com/varsity
o The winning probability is defined as the total number of winning trades divided over the
total number of trades
o The win/loss ratio is the average gain of winning trades divided over average loss of the
negative trades.
To understand this better, let’s take up an example. Assume I have a trading system which
has produced the following results, for sake of simplicity, let’s assume this is a trading system
to trade just one stock, Tata Motors.
Given the above data –
W = Total Number of winners / Total number of trades
= 6/10
=0.6
R = Average Gain / Average Loss
Average gain = Average of [5325, 2312, 4891, 1763, 8675, 4231]
= 4,532
Average loss = Average of [6897, 231, 989, 1980]
=3,274
112 zerodha.com/varsity
R = 4532 / 3274
= 1.384
Do note, a number greater than 1 is always desirable as it indicates that your average gains
are higher than your average loss.
Lets plug these numbers back to the Kelly’s Criterion equation –
Kelly % = W – [(1-W)/R]
= 0.6 – [(1-0.6)/1.384]
=0.6 – [0.4/1.384]
= 0.31 or 31%.
As per the original school of thought – Kelly’s percentage is a direct representation of how
much capital one should expose for a trade. For example, for the 11th trade on Tata Motors,
Kelly’s Criterion suggests a capital exposure of 31%.
But I think this can be a little tricky, imagine a trading system with great accuracy – the Kelly;s
Percentage can turn out to be 70%, suggesting a capital exposure of 70% to the next trade.
Not a very smart thing to do if you ask me. However, you may ask why not? After all a system
with 70% accuracy is a great, so why not maximize the bet?
This is because, there is still a 30% chance to lose 70% of your capital!
Given this, here is a simple modification to Kelly’s criterion. Let us go back to the percentage
risk position sizing technique we discussed earlier in the chapter.
We defined the percentage risk as a technique wherein the exposure to a trade is defined as
1.5% (or any percentage) of the capital. Given Kelly’s criterion, we can modify the exposure
as ‘up to 5%’ (or any percentage you deem suitable).
What does this mean? This means for a given trade, I would not expose more than 5% of the
capital. This also means that capital exposed could range from as low as 0.1% to all the way
up to 5%. So how do I decide?
113 zerodha.com/varsity
We can use Kelly’s percentage here. For example, if the Kelly’s percentage is 30%, then I’d
expose, 30% of 5% or in other words, I’d expose 1.5%. If the Kelly’s percentage is 70%, then
I’d expose 70% of 5% or say 3.5% of the capital on the trade.
So higher the Kelly’s percentage, higher is the capital exposed and vice versa.
For a more Mathematical explanation on Kelly’s Criterion, I’d suggest you watch this video,
if not for anything, watch from the 10th minute onward.
With this, I’d like to close the discussion on position sizing, hopefully the last 4 chapters has
given you a fair understanding of the importance of position sizing and techniques to position
size your bets.
Onwards to ‘Trading and Investing Biases’.
Key takeaways from this chapter
1. Percentage Risk is an easy and intuitive position sizing technique
2. One has to define the maximum amount of risk one as a percentage of capital, dividing
this over the stop-loss gives us a sense of how much capital one should expose to a
trade
3. Kelly’s Criterion suggests how much capital one can expose for a given trade
4. One can combine Kelly’s Criterion with percentage risk for optimal results
114 zerodha.com/varsity
