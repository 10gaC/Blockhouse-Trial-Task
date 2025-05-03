# Blockhouse-Trial-Task

## Introduction

This project implements and back-tests a Smart Order Router (SOR) following the static cost model introduced in Cont & Kukanov (2013). The trading process in today’s automated financial markets can be divided into several stages. 
Once the general strategy is devised, i.e orders are all scheduled, including their type (limit, market...), volume and time of execution, one still needs to specify how each individual order should be placed as traders often have access to 
multiple trading venues, with different parameters. Routing those orders among the available venues is hence a crucial matter to minimize transaction costs and make the most of the trading strategy. 

The SOR splits a 5,000-share buy order across multiple venues based on risk and market data, minimizing expected cost while respecting liquidity constraints. To do so, we look at snapshots of the market, and at each one, the router 
uses a static allocator to choose how many shares to send to each venue. The allocator then minimizes a cost function that penalizes: 
* Overfilling (sending more shares than needed) through $\lambda_{over}$.
* Underfilling (not completing the order) through $\lambda_{under}$.
* Queue position risk (the farther back we are in the line, the riskier) through $\theta_{over}$.

We tune these parameters to find an optimal (or at least, efficient) triplet that allows the router to effectively reduce costs and optimize venue allocation. 

## The dataset 

The dataset we use is l1_day.csv – roughly sixty thousand MBP records covering 13 : 36 : 32–13 : 45 : 14 UTC on 1 Aug 2024.

## Code Structure

The general architecture of the code is the following: 
* The *compute_cost* function computes the cost of a given split, i.e a proposed allocation of the total order size across available venues
* The *allocate* function tries all partitions (with the right size) across venues, computes cost for each split using compute_cost() and returns the split that minimizes total execution cost.
* The *run_backtest* function runs the full router simulation. At each snapshot, it :
   * Calls *allocate()* to determine share split
   * Fills as much as possible up to ask_size
   * Tracks cumulative cost and remaining quantity
   * Returns total cost, filled shares, and average price.

Thus far the above mentioned parameters have all been fixed. In the next steps, we fine-tune them and compare the performance of the router to, simple, more agressive strategies. 

* The *tune_parameters()* function picks the combination of parameters that yield the lowest average execution price and returns it, alongside associated statistics. 

The question that arises is: how does our model perform compared to classic allocation methods, such as best-ask ? To test this, we look at the following: 
* *baseline_best_ask()*, which yields the lowest execution average price using a lowest-ask method.
* *baseline_twap()*, a sixty-second-bucket TWAP strategy.
* *baseline_vwap()*, a VWAP that weights prices by displayed ask size.
* *compare_to_baselines()* yields the upside of using the SOR, rather than the three previous strategies.
* Finally, *plot_cumulative_cost()* plots the cost of trading using SOR with respect to our order status (how far we are)

## Parameters space

  Since we want our code to run relatively fast (maximum of 2 minutes), our parameter space cannot be too large. For this reason, we run a grid search over a 3^3 = 27 triplets to limit computational time and cost. We picked:
`lambda_over ∈ [0.01, 0.05, 0.1]`
`lambda_under ∈ [0.01, 0.05, 0.1]`
`theta_queue ∈ [0.0001, 0.0005, 0.001]`

The first two are set between 0.01 and 0.1 to represent cost penalties of 1–10 cents per share. This aligns with Cont & Kukanov's example values and reflects the real-world scale of slippage or misallocation. The last one is kept very small (fractions of a cent) because queue position risk is subtle but accumulates over large volumes. A higher value here would overweight queue penalties and lead to overly aggressive routing
## Improving filling realism 

Unfortunately, the provided dataset did not allow us to properly assess the model's performance as it only contained one single venue, which makes the whole process rather plain and uninteresting. However, we can look at ways to improve realism of our model as it is still somewhat elementary. These include: 

* Partial queue fills - if one is at the back of the queue at a given venue, often they will not see the full available volume, but only a fraction of the total liquidity. We could easily model this by shrinking the volume at each venue given our position in the queue. 
* Market latency - some venues may respond slower than others. Assigning each venue a probability based on relative latency would allow the allocator to favor faster venues. We could for example compute this probability based on past data.
* Market impact - on assets that are relatively not liquid, market makers and traders can sometimes cause the price if they place a large order. We could think about adding a penalty to account for this effect and encourage the ROS to spread the volume over time. 








