---
title: "Value at Risk"
category: "risk"
source: "Zerodha Varsity"
module: "Risk Management and Trading Psychology"
tags:
  - "equity"
  - "portfolio"
  - "risk"
  - "stocks"
---

## CHAPTER 10

Value at Risk
10.1 – Black Monday
Let’s start this chapter with a flashback. For many of us, when we think of the 70’s, we can
mostly relate to all the great rock and roll music being produced from across the globe.
However, the economists and bankers saw the 70’s very differently.
The global energy crisis of 70’s had drawn the United States of America into an economic
depression of sorts. This lead to a high inflationary environment in the United States followed
by elevated levels of unemployment (perhaps why many took to music and produced great
music). It was only towards the late 70’s that things started to improve again and the
economy started to look up. The Unites States did the right things and took the right steps to
ease the economy, and as a result starting late seventies / early eighties the economy of
United States was back on track. Naturally, as the economy flourished, so did the stock
markets.
Markets rallied continuously starting from the early 1980s all the way to mid-1987. Traders
describe this as one of the dream bull runs in the United Sates. Dow made an all-time high of
2,722 during August 1987. This was roughly a 44% return over 1986. However, around the
same time, there were again signs of a stagnating economy. In economic parlance, this is
referred to as ‘soft landing’ of the economy, where the economy kind of takes a breather.
Post-August 1987’s peak, the market started to take a breather. The months of Aug, Sept, Oct
1987, saw an unprecedented amount of mixed emotions. At every small correction, new
leveraged long positions were taken. At the same time, there was a great deal of unwinding
of positions as well. Naturally, the markets neither rallied nor corrected.
While this was panning on the domestic front, trouble was brewing offshore with Iran
bombing American super tankers stationed near Kuwait’s oil port. The month of October
1987, was one of its kind in the history of financial markets. I find the sequence of events
which occurred during the 2nd week of October 1987 extremely intriguing, there were way too
much drama and horror panning out across the globe –
73 zerodha.com/varsity
 14th Oct 1987 (Wednesday) – Dow dropped nearly 4%, this was a record drop during that
period
 15th Oct 1987 (Thursday) – Dow dropped another 2.5%. Dow was nearly 12% down from
the August 1987’s high. On the other side of the globe, Iran attacked an American super
tanker stationed outside Kuwait’s oil port, with a Silkworm missile
 With these two events, there were enough fear and panic spread across the global
financial markets
 16th Oct 1987 (Friday) – London was engulfed by an unexpected giant storm, winds
blowing at 175 KMPH caused blackouts in London (especially the southern part, which is
the financial hub). London markets were officially closed. Dow opened weak, and crashed
nearly 5%, creating a global concern. Treasury Secretary was recorded stating economic
concerns. Naturally, this would add more panic
 19th Oct 1987 (Black Monday) – Starting from the Hong Kong, markets shaved off points
like melting cheese. Panic spread to London, and then finally to the US. Dow recorded the
highest ever fall with close 508 or 22.61% getting knocked off on a single day, quite
naturally attracting the Black Monday tile.
The financial world had not witnessed such dramatic turn of events. This was perhaps the
very first few ‘Black Swan’ events to hit word hard. When the dust settled, a new breed of
traders occupied Wall Street, they called themselves, “The Quants”.
74 zerodha.com/varsity
10.2 – The rise of quants
The dramatic chain of events of October 1987 had multiple repercussion across the financial
markets. Financial regulators were even more concerned about system wide shocks and
firm’s capability to assess risk. Financial firms were evaluating the probability of a ‘firm-wide
survival’ if things of such catastrophic magnitude were to shake up the financial system once
again. After all, the theory suggested that ‘October 1987’ had a very slim chance to occur, but
it did.
It is very typical for financial firms to take up speculative trading positions across
geographies, across varied counterparties, across varied assets and structured assets.
Naturally, assessing risk at such level gets nothing short of a nightmarish task. However, this
was exactly what the business required. They needed to know how much they would stand
to lose, if October 1987 were to repeat. The new breed of traders and risk mangers calling
themselves ‘Quants’, developed highly sophisticated mathematical models to monitor
positions and evaluate risk level on a real-time basis. These folks came in with doctorates
from different backgrounds – statisticians, physicist, mathematicians, and of course
traditional finance. Firms officially recognized ‘Risk management’ as an important layer in
the system, and risk management teams were inducted in the ‘middle office’ segment, across
the banks and trading firms on Wall Street. They were all working towards the common cause
of assessing risk.
Then CEO of JP Morgan Mr.Dennis Weatherstone, commissioned the famous ‘4:15 PM’ report.
A one-page report which gave him a good sense of the combined risk at the firm-wide level.
This report was expected at his desk every day 4:15 PM, just 15 minutes past market close.
The report became so popular (and essential) that JP Morgan published the methodology
and started providing the necessary underlying parameters to other banks. Eventually, JP
Morgan, spun off this team and created an independent company, which goes by the name
‘The Risk Metrics Group’, which was later acquired by the MSCI group.
The report essentially contained what is called as the ‘Value at Risk’ (VaR), a metric which
gives you a sense of the worst case loss, if the most unimaginable were to occur tomorrow
morning.
The focus of this chapter is just that. We will discuss Value at Risk, for your portfolio.
75 zerodha.com/varsity
10.3 – Normal Distribution
At the core of Value at Risk (VaR) approach, lies the concept of normal distribution. We have
touched upon this topic several times across multiple modules in Varsity. For this reason, I
will not get into explaining normal distribution at this stage. I’ll just assume you know what
we are talking about. The Value at Risk concept that we are about to discuss is a ‘quick and
dirty’ approach to estimating the portfolio VaR. I’ve been using this for a few years now, and
trust me it just works fine for a simple ‘buy and hold’ equity portfolio.
In simple words, Portfolio VaR helps us answer the following questions –
1. If a black swan event were to occur tomorrow morning, then what is the worst case
portfolio loss?
2. What is the probability associated with the worst case loss?
Portfolio VaR helps us identify this. The steps involved in calculating portfolio VaR are very
simple, and is as stated below –
1. Identify the distribution of the portfolio returns
2. Map the distribution – idea here to check if the portfolio returns are ‘Normally
distributed’
3. Arrange portfolio returns from ascending to descending order
4. Observe out the last 95% observation
5. The least value within the last 95% is the portfolio VaR
6. Average of the last 5% is the cumulative VaR or CVar
Of course, for better understanding, let us apply this to the portfolio we have been dealing
with so far and calculate its Value at Risk.
10.4 – Distribution of portfolio returns
In this section, we will concentrate on the first two steps (as listed above) involved in
calculating the portfolio VaR. The first two steps involve us to identify the distribution of the
portfolio returns. For this, we need to deal with either the normalized returns or the direct
portfolio returns. Do recall, we have already calculated the normalized returns when we
discussed the ‘equity curve’. I’m just using the same here –
76 zerodha.com/varsity
You can find these returns in the sheet titled ‘EQ Curve’. I’ve copied these portfolio returns
onto a separate sheet to calculate the Value at Risk for the portfolio. At this stage, the new
sheet looks like this –
Remember, our agenda at this stage is to find out what kind of distribution the portfolio
returns fall under. To do this, we do the following –
Step 1 – From the given time series (of portfolio returns) calculate the maximum and
minimum return. To do this, we can use the ‘=Max()’ and ‘=Min()’ function on excel.
77 zerodha.com/varsity
Step 2 – Estimate the number of data points. The number of data points is quite straight
forward. We can use the ‘=count ()’ function for this.
There are 126 data points, please do remember we are dealing with just last six months data
for now. Ideally speaking, you should be running this exercise on at least 1 year of data. But
as of now, the idea is just to push the concept across.
Step 3 – Bin width
We now have to create ‘bin array’ under which we can place the frequency of returns. The
frequency of returns helps up understand the number of occurrence of a particular return. In
simple terms, it helps us answer ‘how many times a return of say 0.5% has occurred over the
last 126 day?’. To do this, we first calculate the bin width as follows –
Bin width = (Difference between max and min return) / 25
I’ve selected 25 based on the number of observations we have.
= (3.26% – (-2.82%))/25
=0.002431
Step 4 – Build the bin array
78 zerodha.com/varsity
This is quite simple – we start form the lowest return and increment this with the bin width.
For example, lowest return is -2.82, so the next cell would contain
= -2.82 + 0.002431
= – 2.58
We keep incrementing this until we hit the maximum return of 3.26%. Here is how the table
looks at this stage –
And here is the full list –
79 zerodha.com/varsity
We now have to calculate the frequency of these return occurring within the bin array. Let me
just present the data first and then explain what is going on –
80 zerodha.com/varsity
I’ve used the ‘=frequency ()’, function on excel to calculate the frequency. The first row,
suggests that out of the 126 return observation, there was only 1 observation where the
return was -2.82%. There were 0 observations between -2.82% and 2.58%. Similarly, there
were 13 observations 0.34% and 0.58%. So on and so forth.
To calculate the frequency, we simply have to select all the cells next to Bin array, without
deselecting, type =frequency in the formula bar and give the necessary inputs. Here is the
image of how this part appears –
Do remember to hit ‘Ctrl + shift + enter’ simultaneously and not just enter. Upon doing this,
you will generate the frequency of the returns.
Step 5 – Plot the distribution
This is fairly simple. We have the bin array which is where all our returns lie and next to that
we have the frequency, which is the number of times a certain return has occurred. We just
need to plot the graph of the frequency, and we get the frequency distribution. Our job now
is to visually estimate if the distribution looks like a bell curve (normal distribution) or not.
To plot the distribution, I simply have to select the all the frequency data and opt for a bar
chart. Here is how it looks –
81 zerodha.com/varsity
Clearly what we see above is a bell-shaped curve, hence it is quite reasonable to assume that
the portfolio returns are normally distributed.
10.5 – Value at Risk
Now that we have established that the returns are normally distributed, we proceed to
calculate the Value at Risk. From here on, the process is quite straightforward. To do this, we
have to reorganize the portfolio returns from the ascending to descending order.
I’ve used excels sort function to do this. At this stage, I will go ahead and calculate Portfolio
VaR and Portfolio CVaR. I will shortly explain, the logic behind this calculation.
82 zerodha.com/varsity
Portfolio VaR – is defined as the least value within 95% of the observation. We have 126
observations, so 95% of this is 120 observations. Portfolio VaR is essential, the least most
value within the 120 observations. This works out to be -1.48%.
I take the average of the remaining 5% of the observation, i.e the average of the last 6
observations, and that is the Cumulative VaR of CVaR.
The CVaR works out to -2.39%.
You may have many questions at this stage, let me list them down here along with the
answers –
1. Why did we plot the frequency distribution of the portfolio?
1. To establish the fact that the portfolio returns are normally distributed
2. Why should we check for normal distribution?
1. If the data we are studying is normally distributed, then we can characteristics of
normal distribution is applicable to the data set
3. What are the characteristics of normally distributed data?
1. There are quite a few, but you should specifically know that 68% of the data lies within
1 SD, 95% of the data within 2nd, and 99.7% of the data lies within the 3rd I’d suggest
you read this chapter to know more about the normal distribution.
4. Why did we sort the data?
1. We have established that the data set is normally distributed. Do remember, we are
only interested in the worst case scenario. Given this, when we sort it from highest to
lowest, we are essentially in a position to look at the returns in a more systematic way.
5. Why did bother to take only 95% observation?
1. Remember, according to the normal distribution theory, 95% of the data lies within
the 2nd standard deviation. This means on any random day, the return on the portfolio
is likely to be any value within the 95% of the observations. Therefore, quite naturally
the least most value within the 95% observation should represent the worst case loss
or the Value at Risk.
6. What does the VaR of -1.48% indicate?
1. It tells that the worst case loss for the given portfolio is -1.49% and we can conclude
this with a confidence of 95%
7. Can’t the loss not exceed -1.48%?
1. Yes, it certainly can and this is where CVaR comes into play. In the case of an extreme
event, there is a 5% chance that the portfolio could experience a loss of -2.39%.
8. Can’t the loss exceed beyond -2.89%?
83 zerodha.com/varsity
1. Yes, it can but the probability of this occurring is quite very low.
I hope the above discussion makes sense, do apply this on your equity portfolio and I’m sure
you will gain a greater insight into how your portfolio is positioned.
We have discussed quite a few things with respect to the portfolio and the risk associated
with it. We will now proceed to understand risk with respect to trading positions.
Download the Excel workbook used in this chapter.
Key takeaways from this chapter
1. Events which have a very low probability of occurrence is called ‘Black Swan ’events
2. When a black swan event occurs, a portfolio can experience higher levels of losses
3. Value at Risk is one approach to estimate the worst case loss if a black swan event
were to occur
4. We can estimate the portfolio VaR by studying the distribution of the portfolio returns
5. The average of the last 5% of the observation gives us the Value at Risk of the portfolio.
84 zerodha.com/varsity
