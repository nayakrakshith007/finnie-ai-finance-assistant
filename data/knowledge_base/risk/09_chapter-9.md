---
title: "CHAPTER 9"
category: "risk"
source: "Zerodha Varsity"
module: "Risk Management and Trading Psychology"
tags:
  - "equity"
  - "portfolio"
  - "risk"
  - "stocks"
---

## CHAPTER 9

Portfolio Optimization (Part 2)
9.1 – Working with the weights
In the previous chapter we introduced the concept of portfolio optimization using excel’s
solver tool. We will build on the same concept in this chapter and proceed to understand an
important portfolio concept, often referred to as the ‘Efficient Frontier’.
Recall in the previous chapter, we discussed how a portfolio can produce multiple return
series for a fixed portfolio variance. We will now go ahead and see how this works. This
concept will eventually lead us to understanding portfolio optimization better.
In the previous chapter, we optimized the portfolio to produce the minimum variance
portfolio. The results, in terms of weights of individual stocks were as follows –
62 zerodha.com/varsity
And the expected portfolio returns and the portfolio variance is as follows –
Here is where things start to get a little interesting. So far what we have achieved in terms of
portfolio optimization is merely a minimum variance portfolio. Like we discussed in the
previous chapter, for every fixed risk level, there could be multiple unique portfolio with
varying return characteristics. We will now go ahead and explore this in greater detail.
We know at 15.57% portfolio variance, the return expected is 36.35%. We will now go ahead
and increase the risk maybe to 17%, and calculate the highest and lowest possible returns
for this. In other words, we are essentially trying to identify the highest and lowest possible
return for a fixed portfolio variance of 17%. Also, do pay attention here – when I say increase
the risk, we are essentially fixing the risk to certain desired level. 17% for now.
9.2 – More optimization
The general direction we are headed is this – we know the minimum risk possible for this
portfolio is 15.57%. We have also noted the return achievable at this level of risk i.e – 36.35%.
Like I mentioned earlier, we will now increase the risk a notch higher and note down the
maximum and minimum return for this risk. Along with the return, we will also note the
investment weights. We will then increase the risk another notch higher and again note the
max and min return along with the weights. We will do few such iterations and note down all
the observation.
63 zerodha.com/varsity
Eventually, I would like to plot a scatter plot of fixed risk along with its respective max return
and min return data points and study this scatter plot in greater detail. This scatter plot will
help us understand portfolio optimization.
So let us get started by fixing the risk at 17%. Please note, I’ve opted 17% just like that, it
could very well have been 16% or 18%.
Step 1 – Invoke the solver
As I explained in the previous chapter, I’ve invoked the solver calculator by clicking on the
data ribbon. I’ve highlighted the optimized weights for the minimum variance portfolio, this
is just for your reference.
Step 2 – Set the parameters
To begin with let us find out the maximum return one can achieve for a fixed 17% risk. For
this, we need to set the objective to maximize the ‘expected portfolio return’. The same is
highlighted as shown below –
64 zerodha.com/varsity
Step 3 – Select the weights
The next step is to ensure that we tell the solver tool that we want to optimize the portfolio
for maximum return by varying the weights. This is very similar to what we did in the previous
chapter.
Do note, the weights here are the variable cells.
65 zerodha.com/varsity
Step 4 – Set the constraints
Now, here is the important part of the optimization where we set the constraints. We now tell
solver that we need to maximize the returns @ 17% risk, by varying the investment weights.
We do these while keeping the following two constraints –
1. The total weights add up to 100%
2. The Portfolio risk is fixed to 17%
The constraints section now looks like this –
With these constraints loaded and rest of the parameters specified, we can go ahead and click
on ‘solve’ to figure out the maximum return possible @ 17%, along with the respective
weights.
66 zerodha.com/varsity
The result upon optimization is as follows –
The maximum possible returns @17% portfolio variance happens to be 55.87%. However, to
achieve this, the weights are as show above. Notice how the weights for this portfolio has
changes when compared to the minimum variance portfolio.
We will now proceed to figure out the minimum return possible for the same fixed amount of
risk, which is 17% in our case. Before we proceed, here is a table that I’m compiling of all the
various portfolios that we are building, along with its respective weights and risk return
characteristics.
We are now working on portfolio 3 (P3), which is the minimum risk possible for a fixed risk of
17%. Here is the solver tool, fully loaded and ready to be optimized.
67 zerodha.com/varsity
Notice, while other variables remain the same, the objective is shifted to minimize from
maximize. Upon optimization, the return is now minimized to 18.35%. Clearly, for the same
given risk, we have now established two unique portfolios with different possible return
characteristics, all these while just changing the investment weights in the stocks.
Here are the three unique portfolios that we have generated so far –
Just to recall – P1 is the minimum variance portfolio, P2 max risk @17%, and P3 is min risk at
17%.
68 zerodha.com/varsity
9.3 – Efficient Frontier
As discussed earlier, we can now increase the risk a notch higher to maybe 18%, 19%, and
21% and identify the maximum and minimum risk at both these risk levels. Remember, our
end objective is attain a scatter plot of the risk and return profile and study its characteristics.
I’ve gone ahead and optimized the portfolios for all the risk points, and at each point, I’ve
identified the maximum and minimum return possible. Please note, I’ve rounded off the
decimal values here, just so that the table looks pretty
If you notice, I’ve highlighted the risk and return values of each portfolios. I’ll now go ahead
and plot a scatter plot of these data points and see, what I can see.
To plot a scatter plot, simply select the data points and opt for the scatter plot under the
insert ribbon. This is how it looks –
69 zerodha.com/varsity
Once you click on the scatter plot, you will be able to see the how the plot appears. Here is
how it looks, of course, I’ve tried to format the graph to make it look more presentable.
This curve that you see above my friend, is called the ‘efficient frontier’ of this portfolio. So
what do we understand from this curve and why is it so important? Well, quite a few things,
lets deal with it one by one –
1. As you can see, the X-axis represents risk and the Y-axis represents returns
2. Starting from the left most point, the one which seems to be a little isolated from the
rest, represents the minimum variance portfolio. We know this portfolio has a risk of
15.57% with a return of 36.25%.
3. We now move focus to 17% risk (notice the x axis), you can find two plots, one at
18.35% and another at 55.87% – what does this tell you?
1. It tells us that at 17% risk (or when we are particular about fixing the risk at 17%), the
best possible portfolio can achieve a return of 55.87%
2. The worst possible portfolio (in terms of return) is 18.35%
3. In simple terms, when you fix a level of risk you are comfortable, you should aim to
maximize the return
4. There are multiple other portfolios that are possible between 18.35% and 55.87%
(when we fix risk at 17%) these would be represented as plots between the minimum
and maximum return. All these portfolios are considered inefficient, the minimum
return portfolio being the worst amongst the rest
5. So as an investor, your aim should be to maximum the return, especially when you
have some clarity on how much risk you are willing to bear
4. You can notice the same behavior for risks at 18%, 19%m and 21%
70 zerodha.com/varsity
5. The best possible portfolios, or in other words, the efficient portfolio will always lie on
the line above the minimum variance portfolio. This line is highlighted below
So, you as an investor, should always aim to create a portfolio, which lies on the efficient
frontier, and as you may realize, creating this portfolio is merely a function of rearranging
weights as per the results obtained in portfolio optimization.
Think about it – when you risk your money, you obviously want the best possible return,
right? This is exactly what the curve above is trying to convey to us. Its prompting us to create
portfolios more efficiently.
In the next chapter, we will take a quick look at a concept called “Value at risk” and then
proceed to understanding risk from a trader’s perspective.
You can download the excel sheet used in this chapter.
71 zerodha.com/varsity
Key takeaways from this chapter
1. A portfolio with certain weights to each stock is considered unique
2. When we fix the desired level of risk, we can optimize the portfolio to yield the
minimum return and maximum return portfolios
3. Between the min and max return portfolio (for a given fixed level of risk), we can have
multiple unique portfolios
4. The scatter plot of risk and return gives us the efficient frontier
5. For a given level of risk, the best possible portfolio one can construct would lie on the
efficient frontier, all other portfolios are deemed inefficient
72 zerodha.com/varsity
