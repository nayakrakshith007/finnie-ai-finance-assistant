---
title: "Equity Curve"
category: "risk"
source: "Zerodha Varsity"
module: "Risk Management and Trading Psychology"
tags:
  - "equity"
  - "index"
  - "nifty"
  - "portfolio"
  - "risk"
  - "sensex"
  - "stocks"
  - "volatility"
---

## CHAPTER 6

Equity Curve
6.1 – Overview
This is off topic – but a little digression hurts no one, I guess. Of all the chapters I have written
in Varsity, I guess this one will be a very special one for me. Not because of the topic that I
will be discussing. It is because of the place where I’m sitting right now and writing this for
you all. Its 6:15 AM – surrounding me 360 degrees are misty mountains; the landscape I guess
cannot get any better. There is only one shack here with a little music player, playing Bob
Marley’s Redemption Song. Can it get any better? At least not for me I guess
Anyway, back to school
We discussed Portfolio Variance in the previous chapter. It would be pointless to crunch all
the numbers to extract the variance of the portfolio, unless we put that to good use. This is
exactly what we will achieve over the next 2 chapters.
Over the next 2 chapters, we will try and do the following –
36 zerodha.com/varsity
1. Discuss Equity curve and an alternate method to calculate portfolio variance
2. Estimate the portfolio’s expected returns over 1 year
3. Optimize the portfolio for maximum returns and minimum variance
Note, this chapter is a continuation of the discussion panned out in the previous chapters.
You need to know the context here. If you are reading this chapter without knowing what
happened over the last few chapters, then I’d suggest you go back and read those chapters
first.
6.2 – Equity Curve
We will use this opportunity to develop an equity curve for the 5 stock portfolio that we have.
In a very lose sense, a typical equity curve helps you visualize the performance of the portfolio
on a normalized scale of 100. In other words, it will help you understand how Rs.100/-
invested in this portfolio would have performed over the given period. You can further use
this to benchmark the portfolio’s performance against its benchmark – say Nifty 50 or BSE
Sensex.
There are certain attributes which can be extracted out of the equity curve to develop deeper
insights on the portfolio. More on that later.
Let us proceed to build an equity curve for the 5 stock portfolio. Remember, we had the
following stocks and we also assigned random weights to these stock to form our portfolio.
Here are the stock names along with the weightages –
So what does ‘Investment weight’ means? – It represents the percentage of your corpus
invested in the stock. For example, out of Rs.100,000/-, Rs.7,000/- has been invested in Cipla
and Rs.22,000/- has been invested in Alkem Lab. So on and so forth.
37 zerodha.com/varsity
While developing an equity curve, the usual practice is to normalize the portfolio for Rs.100.
This helps us understand how an investment of Rs.100/- in this portfolio behaved during the
period of investment. I have incorporated this in the excel sheet (please note, the excel used
here is a continuation of the excel used in the previous chapter)
Have a look at the image below –
I have introduced a new column next to the daily return column and included the weight of
the respective stock. At the end, you will find two new column being introduced – starting
value pegged at 100 and total weight at 100%.
Starting value – this is basically the amount of money we are starting with. I have set this to
Rs.100/-. This means, out of the 100 Rupees in total corpus, Rupees 7 is being invested in
Cipla, Rupees 16 in Idea, Rupee 25 in Wonderla so on and so forth.
Now, if I add up the individual weights, then they should all add up to 100%, indicating that
100% of Rs.100 is being invested.
We now have to see how the investment in each stock has performed. To help you understand
this better, let’s take up the case of Cipla for now. The weight assigned to Cipla is 7%, which
means out of Rs.100, Rs.7 is invested in Cipla. Based on the daily price movement of Cipla,
our money i.e. Rs.7/- either increases or decreases. It is important to note that, if on day 1, if
Rs.7 becomes, Rs.7.5/- then the following day, our starting price is Rs.7.5 and not Rs.7/-. I’ve
done this on excel for Cipla, and this is how the calculation looks.
On 1st Sept, Cipla was trading at 579.15, this is the day we decided to invest Rs.7 in the stock.
I understand that this is technically not possible, but for the sake of this example, let us just
assume this is possible and proceed. So on day one i.e. 1st Sept, 7 is invested, on 2nd Sept
38 zerodha.com/varsity
Cipla closed at 577.95, down -0.21% from the previous day. This also means we lose -0.21%
on our investment of Rs.7/- making it Rs.6.985. On 6th Sept Cipla shot up by 0.11% to 578.6,
hence we gain 0.11% on 6.985 to make it 6.993. So on and so forth the rest of the data points.
I’ve done this math for all the stocks in portfolio and here is how the table looks –
I’ve calculated the daily fluctuation in the invested price across all stocks and I’ve highlighted
the same in blue.
Now, think about what is happening here – I’ve basically split Rs.100/- across 5 stocks and
invested in different proportions. If I sum up the daily variation in each stock, I should be able
to get the overall daily fluctuation of Rs.100, right? Doing this gives me the overall perspective
on how my portfolio is moving. Let me add these up and see how Rs.100 invested across 5
stocks moves on a daily basis –
Adding up the values on a daily basis gives me the time series of the daily fluctuation of the
portfolio.
An ‘Equity Curve’ (EQ curve) can be developed if you plot the chart of this – i.e. the time series
data of the daily normalized portfolio value. I say normalized because I’ve scaled down the
investment to Rs.100/-.
39 zerodha.com/varsity
So, here is the EQ curve for the portfolio that we have –
As easy as that. Eq curve is a very popular way of visualizing the portfolio performance. It
gives a quick estimate of the returns generated by the portfolio. In this case, we started with
and investment of Rs.100/- and at the end of 6 months the portfolio was valued at 113.84.
Have a look at the image below –
So without much thinking, I know the portfolio has done close to 13.8% during the given
period.
6.3 – Portfolio as a whole
Now, here is something I’d like you to think about. In the previous chapter, we calculated the
portfolio variance. While doing so, one of the key things we had to calculate was the standard
deviation of each stock. Standard deviation as you may know, represents the volatility of the
stock which is nothing but the risk associated with the stock.
To calculate the standard deviation, we used the inbuilt excel function ‘=STDEV()’ applied on
the daily return of the stock. Now, think about this – we anyway have the daily value of the
portfolio (although normalized to Rs.100).
Now imagine the portfolio itself in its entirety, as a whole, as a single stock, and calculate its
daily returns. Just like how we calculated the daily returns of the stocks in the previous
40 zerodha.com/varsity
chapter. Further, what if I apply the ‘=STDEV()’ function on the portfolio’s daily return? The
resulting value should be the standard deviation of the portfolio which in other words should
represents risk also called as Variance of the portfolio.
Are you able to sense where we are heading? Yes, we are talking about calculating portfolio
variance using a different approach all together
To help you comprehend this better, let me paste the portfolio variance value we calculated
in the previous chapter–
We calculated the above value using the matrix multiplication and the correlation matrix
technique.
We will now look at the portfolio as a whole and calculate the daily returns of the normalized
portfolio value. The standard deviation of the portfolio’s daily returns should yield us a value
equal to or somewhere near the portfolio variance calculated previously.
I’ve included a new column next to the daily normalized portfolio value and calculated the
Portfolio’s daily returns –
Once I have the returns in place, I will apply the standard deviation function on the time series
data, this should yield a value close to the portfolio variance value we previously calculated.
41 zerodha.com/varsity
So there you go, the STDEV function gives us the exact same value!
You can download the excel sheet used in this chapter. In the next chapter, we will use the
portfolio variance to estimate the expected returns along with optimization.
Quick Task – I’d like to leave you with a quick task here. We have assigned random weights
to the stocks. Go ahead and change the weights of the stocks and see the impact on the
overall returns. Do share your observation in the comment box below.
Key takeaways from this chapter
1. An equity curve is a standard way to visualize the performance of a portfolio
2. A standard industry wide practice is to normalize the portfolio to a starting investment
value of Rs.100/-
3. We assign weights and the respective investment to each stock
4. We need to calculate the daily change in investment value in each stock
5. The sum total of all the variation in each stock adds up to the variation of the entire
portfolio
6. The graph of the change in daily prices of the portfolio yields the equity curve
7. We can look at the portfolio as a whole, as a single stock and calculate its SD
8. The SD of portfolio also yields the portfolio variance
42 zerodha.com/varsity
