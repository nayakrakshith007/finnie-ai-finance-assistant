---
title: "Risk (Part 4) - Correlation Matrix & Portfolio"
category: "risk"
source: "Zerodha Varsity"
module: "Risk Management and Trading Psychology"
tags:
  - "equity"
  - "portfolio"
  - "risk"
  - "stocks"
---

## CHAPTER 5

Risk (Part 4) – Correlation Matrix & Portfolio
Variance
5.1 – Correlation Matrix
In the previous chapter, we successfully calculated the variance co variance matrix. As we
discussed, these numbers are too small for us to make any sense. Hence, as a practice, it
always makes sense to calculate the correlation matrix when we calculate the variance
covariance matrix.
So let us go ahead and do this.
How is the correlation between two stocks calculated? Well, hopefully from the previous
chapter, you will recall the formula for correlation –
Where,
Cov (x,y) is the covariance between the two stocks
27 zerodha.com/varsity
σ = Standard deviation of stock x
σ = Standard deviation of stock y
This works fine if we have 2 stocks in the portfolio, but since we have 5 stocks in the portfolio,
we need to resort to matrix operation to find correlations. So, when we have multiple stocks
in the portfolio, the correlations between stocks are all stacked up in a n x n (read it as n by
n) matrix. For example, if it is a 5 stock portfolio (5 being the n here), then we need to create
a 5 x 5 matrix.
The formula for calculating the correlation remains the same. Recall, from the previous
chapter, we have the variance-covariance matrix. For the sake of convenience, I’ll paste the
image again here –
This takes care of the numerator part of the formula. We need to now calculate the
denominator, which is simply the product of the standard deviation of stock A with the
standard deviation of stock B. If the portfolio has 5 stock, then we need the product of the
standard deviation of all possible combination between the stocks in the portfolio.
Let’s go ahead and set this up.
We first need to calculate the standard deviations of each of the stocks in the portfolio. I’m
assuming you are familiar how to do this. You just need to use the ‘=Stdev()’ function on the
daily returns array to get the standard deviations.
I’ve calculated the same on excel used in the previous chapter. Here is the image –
28 zerodha.com/varsity
Given that we have the stock specific standard deviations; we now need to get the product of
the standard deviation of all possible portfolio combination. We resort to matrix
multiplication for this. This can be easily achieved by multiply the standard deviation array
with the transpose of itself.
We first create the matrix skeleton and keep all the cells highlighted –
Now, without deselecting the cells, we apply the matrix multiplication function. Note, we are
multiplying the standard deviation array with the transpose of itself. The image below should
give you an idea, do look at the formula used –
As I mentioned in the previous chapter, whenever you use matrix or array function in excel,
always hold the ‘ctrl+shit+enter’ combo. The resulting matrix looks like this –
29 zerodha.com/varsity
At this point let me paste the formula for the correlation again –
The numerator is the variance covariance matrix as seen below, and the denominator is the
product of the standard deviations which we have just calculated above –
Dividing the variance co-variance matrix by the product of the standard deviations should
result in the correlation matrix. Do note, this is an element by element division, which is still
and array function, so the use of ‘ctrl+shit+enter’ is necessary.
30 zerodha.com/varsity
The resulting correlation matrix looks like this –
The correlation matrix gives us the correlation between any two stocks. For example, if I have
to know the correlation between Cipla and Alkem, I simply have to look under the intersecting
cell between Cipla and Alkem. There are two ways you can do this –
1. Look at the row belonging to Cipla and scroll till the Alkem column
2. Look at the row belonging to Alkem and scroll till the Cipla column
Both these should reflect the same result i.e. 0.2285. This is quite obvious since correlation
between stock A with Stock B is similar to the correlation of Stock B with Stock A. For this
reason, the matrix displays symmetrically similar values above and below the diagonal.
Check this image below, I have highlighted the correlation between Cipla and Alkem and
Alkem and Cipla –
31 zerodha.com/varsity
The correlations along the diagonal represents the correlation of certain stock with itself. Do
note, the correlation numbers above the diagonal is symmetrically similar to the correlation
numbers below the diagonal.
Needless to say, correlation of Stock A with Stock A is always 1, which is what we have got in
the diagonal and the same is highlighted in yellow boxes.
5.2 – Portfolio Variance
We are just few steps away from calculating the Portfolio Variance. As I have discussed earlier,
we need the portfolio variance to identify the extent of risk my portfolio is exposed to. With
this information, I’m no longer driving blind. In fact, one can develop many other insights
based on this. Of course, we will talk about this going forward.
The first step in calculating portfolio variance is to assign weights to the stocks. Weights are
simply the amount of cash we decide to invest in each stock. For example, if I have Rs.100,
and I decide to invest all of that money in Stock A, then the weight in stock A is 100%.
Likewise, if I decide to invest Rs.50 in A, Rs.20 in B, and Rs.30 in C, the weights in A, B, and C
would be 50%, 20%, and 30% respectively.
I have arbitrarily assigned weights to the 5 stocks in the portfolio –
o Cipla @ 7%
o Idea @ 16%
o Wonderla @ 25%
o PVR @ 30%
o Alkem @ 22%
Clearly, there is no science to assigning weights at this stage. However, at a later point in the
module I will discuss more about this part.
32 zerodha.com/varsity
The next step is to calculate the weighted standard deviation. The Weighted standard
deviation is simply the weight of a stock multiplied by its respective standard deviation. For
example, Cipla’s standard deviation is 1.49%, hence its weighted standard deviation would
be 7% * 1.49% = 0.10%
Here are the weights and the weighted standard deviation of 5 stocks in the portfolio –
Do note, the total weight should add up to 100% i.e. the sum of the individual weights in
stocks should add up to 100%.
At this stage, we have all the individual components needed to calculate the ‘Portfolio
Variance’. The formula to calculate the Portfolio Variance is as shown below –
Portfolio Variance = Sqrt (Transpose (Wt.SD) * Correlation Matrix * Wt. SD)
Where,
Wt.SD is the weights standard deviation array.
We will implement the above formula in 3 steps –
1. Calculate the product of Transpose of Wt.SD with correlation matrix. This will result in a row
matrix with 5 elements
2. Multiply the result obtained above (row matrix) with the weighted standard deviation array.
This will result in a single number
3. Take the square root of the result obtained above to get the portfolio variance
So, let’s jump straight ahead and solve for portfolio variance in the same order –
I will create row matrix called ‘M1’ with 5 elements. This will contain the product of the
Transpose of Wt.SD with correlation matrix.
33 zerodha.com/varsity
Do note, you will have to select the empty array space and hold down the ctrl+shift+enter
keys simultaneously.
We now create another value called ‘M2’, which contains the product of M1 and weighted
standard deviation –
34 zerodha.com/varsity
We obtain the value of M2 as 0.000123542, the square root of this value is the portfolio
variance.
The result for the above operation yields a value of 1.11%, which is the portfolio variance of
the 5 stocks portfolio.
Phew!!
I need a break at this. Let’s figure out the next steps in the next chapter J
Download the excel sheet used in this chapter.
Key takeaways from this chapter –
1. Correlation matrix gives out the correlation between any two stocks in a portfolio
2. Correlation between stock A with stock B is the same as the correlation between stock
B with stock A
3. Correlation of a stock with itself is always 1
4. The diagonals of a correlation matrix should represent the correlation of stock A with
itself
5. The correlation matrix contains symmetrical values above and below the diagonals
35 zerodha.com/varsity
