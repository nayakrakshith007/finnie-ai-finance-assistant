---
title: "Position Sizing for active traders (Part 3)"
category: "risk"
source: "Zerodha Varsity"
module: "Risk Management and Trading Psychology"
tags:
  - "equity"
  - "index"
  - "nifty"
  - "portfolio"
  - "risk"
  - "stocks"
  - "volatility"
---

## CHAPTER 13

Position Sizing for active traders (Part 3)
13.1 – Choose your path
We addressed a very crucial concept in the previous chapter. We looked at how one can
determine equity based on 3 different models. Each of these three models on its own merit
imposes some sort of position sizing discipline, but clearly that’s not enough. We still need a
standalone method to position size. Given this, we will move forward to discuss some of Van
Tharp’s techniques on position sizing.
I’d like to talk about three core position sizing techniques at this point, they are –
1. Unit per fixed amount
2. Percentage margin
3. Percentage of volatility
Do note, these models are asset independent and time frame independent. What do I mean
by this? This means that you can apply these position sizing techniques to any asset you
want. It could be stocks, stock futures, commodity futures, or currency futures. Further you
99 zerodha.com/varsity
can apply them across any time frame – intraday, few trading session, or even trades
extending for over few months.
To understand this really well, I’d suggest you pick a trading system, it could be as basic as a
moving average crossover system. Identify entry and exit rules and evaluate the returns you
would generated for the given time period. Now for the same set of data, apply one of the
position sizing technique (which we will shortly discuss) and evaluate the performance. I’m
sure, you will observe a huge improvement not just in terms of P&L but also the stability of
the system.
Just to throw some light into how complex this can get –
 Assume you have a trading system – a simple moving average cross over system
 You intend to deploy cash on this and start trading every signal that the system generates
 There are 3 models to define equity and there are at least 3 basic models to define position
sizing techniques
 This means you can position size in 3 x 3 = 6 different ways to deploy cash for the same
opportunity (signal)
 The P&L for each will be different
However, from my experience, I would suggest you stick one method to estimate equity and
maybe 1 or at the most 2 (meaningful) techniques to position size. Anything more may not be
a great, in the sense, it would induce complexity, and complex does not necessarily mean
better.
So you as a trader need to assess which path to follow based on your temperament. Anyway,
let’s get started on the core position sizing techniques.
13.2 – Unit per fixed amount
Let’s discuss the ‘Unit per fixed amount’ model first. This is a fairly simple model. Any trader
who has a slight inkling towards position sizing would have explored this model in the initial
days. I like and dislike this model for the same reason – its simplicity.
The model requires you to simply state how many shares or lots (in case of futures) you will
trade for a given amount. For example, assume you have Rs.200,000 in your trading account
and you have the following 5 assets (futures) as your opportunity universe –
1. Nifty
100 zerodha.com/varsity
2. SBI
3. HDFC
4. Tata Motors
5. Infosys
You could simply state that you would not want to trade more than 1 lot of futures per 100,000
of any asset at any given point. Given this, assume you get a signal to buy Nifty, now since
there is 2L in the account, you can choose to buy one or 2 lots.
The best part about this model is that it does not complicate the decision-making process.
However, there are few problems with this model.
Consider this – the trading system that you follow generates a signal to buy Nifty Futures and
at the same time the system signals you to buy Tata Motors. Since you have 2L in your
account, you decide to buy 1 lot each. Do note at the point of writing this article, Nifty Futures
requires a margin of about 60K and Tata Motors around 72K.
Irrespective of the margin, the rule simply states, 1 lot per 1L. This means, position sizing rule
is assigning an equal weight to both the contracts, ignoring the implicit ‘riskiness’ of the
asset. To give you a perspective, Nifty Futures has an annualized volatility of around 14% and
Tata Motors has an annualized volatility of over 40%. So essentially, you are exposing yourself
to a higher risk at the portfolio level.
This in fact, is both good and bad at the same time. Good in the sense that it does not reject
a trade based on the riskiness and bad in the sense it does not really factor in risk.
There is another angle here – think about this, consider you are following a trading system to
which you apply the 1 lot per 100,000 position size rule. Assume you have a 2 lac capital. Now,
further assume that the system performs really well and you are bestowed with multiple
winning trades. Now, for each signal, the maximum number of lots you can buy is restricted
to just 2. For you to increase another lot or 2, you really need to double your capital or wait
for your profits to double up you capital. So in a sense this particular position sizing
technique limits the scalability of a system. The only antidote to this is to bring in a much
larger account size.
For these reasons, I kind of don’t prefer the ‘unit per fixed amount’ position sizing technique.
However, please don’t take my word, I’d suggest you work around and figure out your
comfort level with this technique before deciding to adopt or not adopt this as your core
position sizing technique.
101 zerodha.com/varsity
13.3 – Percentage Margin
The percentage margin is an interesting position sizing technique. I personally think this
technique is far more structured than the ‘unit per fixed amount’, technique especially for
intraday traders. The percentage margin technique requires you to position size based on the
margins.
Here you essentially fix a ‘X’ percentage of your capital as margin amount to any particular
trade. Let’s work with an example to understand this better.
Assume you have a capital of Rs.500,000/-, with this you decide that you will not expose more
than 20% as margin amount to a particular trade. This translates to a capital of Rs.100,000/-
per trade.
Assume you spot an opportunity to trade Nifty Futures, you can easily take this position as
the margins for this is roughly around 60K. However, let’s say you spot an opportunity in
ICICI, you will be forced to let go of this as the margin for this is close to Rs.105,000/-. This
means, ICICI will be out of your trading universe until and unless you increase your capital.
Obviously, one should not randomly increase the capital just to accommodate opportunities.
Capital should increase as an outcome on profits accumulating in your account.
Anyway, after you initiate the position in Nifty, assume you spot an opportunity in ACC, the
margin for this is 90K.
Will you take this position?
The answer to this really depends on the way you estimate equity.
If you consider the total equity model, then you will still consider your capital to be 5L, 20%
of which is 1L, hence you can safely take the position in ACC.
However, if you consider the reduced total equity model, then this is how it would work
(assuming 20% position sizing rule) –
Starting Capital = 5L
Margin blocked = 60K
New capital = 4.4L
Margin @ 20% = 88K
102 zerodha.com/varsity
Given this, you’d fall short by (just) 2K for a 90K position, hence you would have to let go…and
as you realize, equity estimation plays very crucial role here.
Lastly, assume, you spot an opportunity which requires a margin of 40K, since you have 88K,
you can comfortably take up 2 lots of this position.
So on and so forth.
The percentage margin rule ensures you pay roughly the same margin to all positions.
However, the volatility from each position could vary. You could end up with risky bets and
therefore altering the entire risk profile of your account.
This exposure to risk is overcome by next position sizing model.
13.4 – Percentage Volatility
The percentage volatility rule accounts for volatility of the underlying asset. The volatility as
per this technique is not really the ‘standard deviation’, but rather the daily expected
movement in the underlying.
For example, if SBI’s OHLC is 276, 279, 274, and 278, then the volatility for the day is simply
the difference between low and high i.e
279 – 274
= 5
To get a sense of the generic volatility measured this way, I can look at the difference between
low and high for last ‘n’ days and take an average. However, the only problem here would be
that I would be ignoring the gap up and gap down openings. For this reason, Van Tharp
suggest the use of ‘Average True Range’ to measure the stock’s volatility.
The ‘Percentage Volatility’ method of position sizing requires us to define the maximum
amount of volatility exposure one can assume for the given equity capital.
For example, if the equity capital is Rs.500,000/- then I could make a rule saying that I do not
want to expose more than 2% of the capital to volatility.
Let’s work with an example. Here is the chart of Piramal Enterprises Limited (PEL) –
103 zerodha.com/varsity
The 14-day ATR is 76. This means each share of PEL contributes to a fluctuation (volatility) of
Rs.76/- to my equity capital.
Now assume I spot an opportunity to trade PEL, the question is how many share should I buy
considering my equity is 5L and I’ve capped volatility exposure as not more than 2%.
2% of 5L is 10,000/-. This means I should only so many number of shares of PEL, such that the
overall volatility caused by PEL is not more than 10k.
Given this, I simply have to divide 10,000 by 76 to find out the number of shares that I can buy
10,000/76
= 131.57 or about 131 shares.
PEL is currently trading around 2700, which means to say, your overall exposure would be –
131 * 2700
=Rs.353,700/-
104 zerodha.com/varsity
I’d suggest you stick to the reduced total equity model for estimating equity here. This
means, the capital available for the next trade would be –
500,000 – 353,700
=146,300
Now @ 2% volatility, the capital exposure reduced to Rs.2929/-. Clearly the capital exposure
to the next trade would reduce, but the exposure to volatility would remain the same.
Here is an advice (from Van Tharp, of course) if you are inclined to follow percentage volatility
technique – the do estimate the total amount of volatility you want to expose your portfolio
too. If the number is say 15% then on a 5L capital this works out to Rs.75,000/-.
Think about it, if every position goes against you, then you stand to lose 75k on a capital of
5L on a single day. How does that feel? If your stomach churns, then 15% portfolio volatility
maybe a bit high for you.
In the next chapter, we will explore few more concepts before we proceed to understanding
‘Trading biases’.
Key takeaways from this chapter
1. Estimating equity plays an important part in position sizing
2. Suppose you have 3 ways to estimate equity and 4 ways to position size, then
essentially you have a 4 x 3 = 12 position sizing technique
3. Unit fixed model requires you to ascertain how many shares or lots you will trade for
every ‘x’ amount of capital in your account
4. Unit fixed model does not consider risk
5. Percentage margin method requires you to define the maximum margin amount you
will expose your capital to. You ideally should club this with total reduced equity
model
6. Percentage volatility measures volatility in term or ATR.
7. Percentage volatility equal weights ‘volatility’ exposure to each position
105 zerodha.com/varsity
