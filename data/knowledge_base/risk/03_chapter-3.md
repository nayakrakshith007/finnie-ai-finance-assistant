---
title: "Risk (Part 2) - Variance & Covariance"
category: "risk"
source: "Zerodha Varsity"
module: "Risk Management and Trading Psychology"
tags:
  - "equity"
  - "portfolio"
  - "risk"
  - "stocks"
  - "volatility"
---

## CHAPTER 3

Risk (Part 2) – Variance & Covariance
3.1. Variance
In the previous chapter, we touched upon the topic of expected return, continuing on it, we
will understand the concept of ‘Portfolio variance’. Portfolio Variance helps us understand
the risk at a portfolio level. I’m hoping you are familiar with ‘Standard Deviation’ as a measure
of risk. We have discussed standard deviation multiple times in the previous modules (refer
to Module 5, chapter 15 onwards). I’d suggest you get familiar with it if you are not already.
While we can easily measure the risk of a single stock by calculating its standard deviation,
calculating the risk of a portfolio is a whole different ball game. When you put a few individual
stocks together and create a portfolio, it becomes a different animal altogether. The agenda
for this chapter is to help you understand how to estimate risk at a portfolio level.
However, before we proceed, we need to understand the concept of Variance and Covariance.
Both Variance and Covariance are statistical measures. Let’s deal with the Variance first.
The variance of stock returns is a measure of how much a stock’s return varies with respect
to its average daily returns. The formula to calculate variance is quite straight forward –
10 zerodha.com/varsity
Where,
σ2 = Variance
X = Daily return
µ = Average of daily return
N = Total number of observation
Note, the variance is measured as sigma squared; I will not get into the reasons for this as the
explanation is quite complex and we could digress. For now, I’d request you to be aware of
the fact that variance is sigma squared. Anyway, calculating variance is quite simple, I’ll take
a simple example to help us understand this better.
Assume the daily return for a stock for 5 consecutive days is as below –
Day 1 – + 0.75%
Day 2 – + 1.25%
Day 3 – -0.55%
Day 4 – -0.75%
Day 5 – +0.8%.
In this case, the average return is +0.3%. We now need to calculate the dispersion of daily
return over its average return, and also square the dispersion.
Daily Return Dispersion from average Dispersion squared
+ 0.75% 0.75% – 0.3% = + 0.45% 0.45%^2 = 0.002025%
+ 1.25% +1.25% – 0.3% = + 0.95% 0.95%^2 = 0.009025%
-0.55% -0.55% – 0.3% = -0.85% -0.85%^2 = 0.007225%
-0.75% -0.75% – 0.3% = -1.05% -1.05%^2 = 0.011025%
11 zerodha.com/varsity
Daily Return Dispersion from average Dispersion squared
+0.80% +0.8% – 0.3% = +0.5% 0.50%^2 = 0.002500%
We now sum up the dispersion squared to get 0.0318000%. We divide this over 5 (N) to get
the variance i.e.
0.0318000% / 5
σ2 = 0.0063600%.
So what does this number tell us? It gives us a sense of how the daily returns are spread out
from the average expected returns. So you as an investor should look into the variance to
determine the riskiness of the investment. A large variance indicates that the stock could be
quite risky while a small variance can indicate lesser risk. In the above example, I would
consider the variance high, since we are looking at just 5 days’ worth of data.
Now, here is something you may be interested in knowing. Variance and standard deviation
are related to each other by the following simple mathematical relationship –
Square Root of Variance = Standard Deviation
We can apply this to the example above and calculate the 5-day standard deviation of the
stock,
~ 0.8%
which is the standard deviation a.k.a. the volatility of the stock (over the last 5 days). Anyway,
at this point, I want you to be aware of Variance and what it really means. We will eventually
plug variance along with covariance into the portfolio variance equation.
3.2 – Covariance
Covariance indicates how two (or more) variables move together. It tells us whether the two
variables move together (in which case they share a positive covariance) or they move in the
opposite direction (negatively covariance). Covariance in the context of stock market
measures how the stock prices of two stocks (or more) move together. The two stocks prices
are likely to move in the same direction if they have a positive covariance; likewise, a negative
covariance indicates that they two stocks move in opposite direction.
12 zerodha.com/varsity
I understand covariance may sound similar to ‘correlation’, however, the two are different.
We will discuss more on this further in the chapter.
I guess calculating the covariance for two stocks will help us get a grip on understanding
covariance better. The formula to calculate covariance of two stocks is as follows –
Where,
Rt S1 = Daily stock return of stock 1
Avg Rt S1 = Average return of stock 1 over n period
Rt S2 = Daily stock return of stock 2
Avg Rt S2 = Average return of stock 2 over n period
n – The total number of days
In other words, you can calculate the covariance between two stocks by taking the sum
product of the difference between the daily returns of the stock and its average return across
both the stocks.
Sounds confusing? I guess so.
Let us take up an example and see how we can calculate the covariance between two stocks.
For the sake of this illustration, I’ve selected two stocks – Cipla Limited and Idea Cellular
Limited. To calculate the covariance between these two stocks, we need to work around with
the above formula. We will resort to good old excel to help us implement the formula.
Before we proceed, if you were to guess the covariance between Cipla and Idea, what do you
think it would be? Think about it – two large corporate, similar size, but in two completely
unrelated sectors. What do you think would be the covariance? Give it a thought.
Anyway, here are the steps involved in calculating covariance in excel (note, although there
is a direct function in excel to calculate covariance, I’ll take the slightly longer approach, just
to ensure clarity) –
Step 1 – Download the daily stock prices. For the purpose of this illustration, I’ve downloaded
6 months’ data for both the stocks.
13 zerodha.com/varsity
Step 2 – Calculate the daily returns for both the stocks. Daily returns can be calculated by
dividing today’s stock price over yesterday’s stock price and subtracting 1 from the result of
this division
Step 3 – Calculate the average of the daily returns
Step 4 – Once the average is calculated, subtract the daily return by its average
Step 5 – Multiply the two series calculated in the previous step
14 zerodha.com/varsity
Step 6 – Sum up the calculation made in the previous step. Take a count of the number of
data points. You can do this by using the count function in excel and giving any of the fields
as the input array. I’ve used the count on the dates here.
Step 7 – This is the final step in calculating the covariance. To do so, one needs to divide the
sum by count minus 1 i.e. (n-1). The count, in this case, is 127, so count-1 would be 126. Sum
calculated in the previous step was 0.006642. Hence, covariance would be
= 0.006642/126
= 0.00005230
You can download the excel sheet.
As you can see, the covariance number is quite small. However, that’s not the point here. We
only look at whether the two stocks share a positive or negative covariance. Clearly, since the
two stocks share a positive covariance, it means that the returns of the two stocks move in
similar directions. It means that for a given situation in the market, both the stocks are likely
15 zerodha.com/varsity
to move in the same direction. Note – covariance does not tell us the degree to which the two
stocks move. The degree or magnitude is captured by correlation. The correlation between
Idea and Cipla is 0.106, which indicates that the two stocks are not tightly correlated.
By the way, here is something very interesting fact. The mathematical equation for
correlation between two stocks is as follows –
Where,
Cov (x,y) is the covariance between the two stocks
σx = Standard deviation of stock x
σy = Standard deviation of stock y
Note, the standard deviation of a stock is simply the square root of the variance of the stock.
Here is a task for you – we have calculated the correlation between Idea and Cipla using the
direct excel function. Can you confirm the accuracy by implementing the formula?
Anyway, in the case of building a stock portfolio, do you think a positive covariance is good
or bad? Or rather do portfolio managers desire stocks (in their portfolio) which share a
positive covariance or they don’t? Well, portfolio managers strive to select stocks which share
a negative covariance. The reason is quite simple – they want stocks in the portfolio which
can hold up. Meaning if one stock goes down, they want, at least the other to hold up. This
kind of counter balances the portfolio and reduces the overall risk.
Now, think about a regular portfolio – it will certainly contain more than 2 stocks. In fact, a
good portfolio will contain at least 12-15 stocks. How would one measure covariance in this
case? This is where things start getting complicated. One will have to measure covariance of
each stock with all the other stocks in the portfolio. Let me illustrate this with a 4 stocks
portfolio. Assume the portfolio is like this –
1. ABB
2. Cipla
3. Idea
4. Wipro
16 zerodha.com/varsity
In this case, we need to calculate the covariance across –
1. ABB, Cipla
2. ABB, Idea
3. ABB, Wipro
4. Cipla, Idea
5. Cipla, Wipro
6. Idea, Wipro
Note, the covariance between stock 1 and stock 2 is the same as the covariance between
stock 2 and stock 1. So as you can see, 4 stocks require us to compute 6 covariances. You can
imagine the complexity when we have 15 or 20 stocks. In fact, when we have more than 2
stocks in the portfolio, the covariance between them is calculated and tabulated using a
‘Variance – Covariance Matrix’. I would love to talk about this now, but I guess, I’ll will keep it
for the next chapter.
Stay tuned for more!
Key takeaways from this chapter
1. Variance measures the dispersion of returns over the expected average returns
2. Higher variance indicates higher risk, lower variance indicates lower risk
3. Square root of variance is standard deviation
4. Covariance between the returns of two stock measures how the returns of the two
stocks vary
5. A positive covariance indicates that the returns move positively and a negative
covariance indicates that while one stock returns moves up, the other comes down
6. Correlation measures the strength of the movement
7. Covariance between two stocks divided over their individual standard deviations
results in a correlation between two stocks.
8. When we have more than 2 stocks in a portfolio, we compute the variance-covariance
using a matrix
17 zerodha.com/varsity
