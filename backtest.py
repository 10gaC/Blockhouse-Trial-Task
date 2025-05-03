# %% [markdown]
# # Blockhouse Quant Strategist Intern Task - Cont & Kukanov Back-testing

# %% [markdown]
# ## Imports

# %%
import numpy as np 
import pandas as pd
import itertools
import os
import json
import matplotlib.pyplot as plt

# %%
# os.chdir("C:/Users/tenga/Downloads/Projects/Blockhouse Quant Strat Trial Task") #put the datafile in the current directory 

# %% [markdown]
# ## Allocation Algorithm

# %% [markdown]
# ### Computing the cost of a given allocation

# %%
def compute_cost(split, venues, order_size, lambda_over, lambda_under, theta_queue):
    cost = 0
    total_executed = 0

    asks = np.array([v['ask'] for v in venues])
    ask_sizes = np.array([v['ask_size'] for v in venues])
    fees = np.array([v['fee'] for v in venues])
    rebates = np.array([v['rebate'] for v in venues])
    
    split = np.array(split)
    executed = np.minimum(split, ask_sizes) #cannot execute more orders than what's available at the venue 
    unfilled = np.maximum(split - ask_sizes, 0) #number of orders we could not execute at the venue 
    cost = np.sum(executed * (asks + fees) - unfilled * rebates) #the cost is the number of executed orders * the price, minus a potential rebate if
        #any order could not be executed
        
    cost += theta_queue * np.sum(split) #queue position risk 
    total_executed = np.sum(executed)

    if total_executed < order_size:
        cost += lambda_under * (order_size - total_executed) #underfill
    elif total_executed > order_size:
        cost += lambda_over * (total_executed - order_size) #overfill

    return cost

# %% [markdown]
# ### Finding the optimal allocation and cost 

# %%
def allocate(order_size, venues, lambda_over, lambda_under, theta_queue):
    n = len(venues)
    step = 25

    best_split = None
    best_cost = float('inf')

    for split in itertools.product(range(0, order_size + step, step), repeat=n): #loop over every possible way to divide shares in 100-share chunks to the n venues
        if abs(sum(split) - order_size) > step: #the combinations needs to meet the order size we seek
            continue

        cost = compute_cost(split, venues, order_size, lambda_over, lambda_under, theta_queue) #computing the cost of the combination
        if cost < best_cost: #optimizing the cost 
            best_cost = cost
            best_split = split
    if best_split is None:
        return [0] * len(venues), float('inf')
    return list(best_split), best_cost

# %% [markdown]
# ## Processing the message-by-message feed 

# %%
def process_snapshots(csv_path):
    df = pd.read_csv(csv_path)

    df = df.sort_values('ts_event') #ordering by ts_event

    df = df.drop_duplicates(subset=['ts_event', 'publisher_id'], keep='first') # for each ts_event, we're keeping the first message of each publisher

    snapshots = []
    for ts, group in df.groupby('ts_event'):
        venues = []
        for _, row in group.iterrows():
            ask = row['ask_px_00'] #venue's best ask 
            ask_size = row['ask_sz_00'] #venue's displayed size
            venue_id = row['publisher_id'] #venue key

            # Filter out missing/invalid entries
            if pd.isna(ask) or pd.isna(ask_size) or ask_size <= 0:
                continue

            venues.append({
                'ask': ask,
                'ask_size': ask_size,
                'venue_id': venue_id,
                'fee': 0.0,     
                'rebate': 0.0 
            })

        if venues:
            snapshots.append(venues)

    return snapshots

# %% [markdown]
# ## Evaluating a parameter triplet (lambda_over, lambda_under, theta_queue) on a 5000-share order

# %%
def run_backtest(snapshots, lambda_over, lambda_under, theta_queue, order_size=5000):
    remaining = order_size
    total_cash = 0
    total_filled = 0
    fill_history = [] 
    cumulative_cost = [0]
    shares_filled = [0]

    for venues in snapshots:
        if remaining <= 0: #already bought 5000 shares
            break
        split, _ = allocate(
            order_size=remaining,
            venues=venues,
            lambda_over=lambda_over,
            lambda_under=lambda_under,
            theta_queue=theta_queue
        ) #how to split the remaining shares across the venue for the parameter we're using
        for i, venue in enumerate(venues):
            fill_qty = min(split[i], venue['ask_size']) #how much can we buy at this venue
            fill_price = venue['ask']
            total_cash += fill_qty * fill_price #how much cash we spent on this venue
            remaining -= fill_qty
            total_filled += fill_qty #how many shares we bought on this venue
            fill_history.append((total_filled, total_cash))
            shares_filled.append(total_filled)

            if remaining <= 0: #once again, already bought 5000 shares
                break
        cumulative_cost.append(total_cash)

    avg_price = total_cash / total_filled if total_filled else 0.0 #average price we'd pay to fill the order we want to place

    return {
        "total_cash": total_cash,
        "avg_price": avg_price,
        "fill_history": fill_history,
        "filled": total_filled,
        "cumulative_cost": cumulative_cost,
        "shares_filled": shares_filled
    }

# %% [markdown]
# ## Tuning the parameters 

# %%
def tune_parameters(snapshots, order_size=5000):
    lambda_over_values = [0.01, 0.05, 0.1]
    lambda_under_values = [0.01, 0.05, 0.1]
    theta_queue_values = [0.0001, 0.0005, 0.001]

    best_result = None
    best_params = None

    for lo in lambda_over_values:
        for lu in lambda_under_values:
            for tq in theta_queue_values:
                result = run_backtest(
                    snapshots,
                    lambda_over=lo,
                    lambda_under=lu,
                    theta_queue=tq,
                    order_size=order_size
                )
                #always choose more complete fills, or cheaper ones if tied
                if (
                    best_result is None or
                    result["filled"] > best_result["filled"] or
                    (result["filled"] == best_result["filled"] and result["total_cash"] < best_result["total_cash"])
                ):
                    best_result = result
                    best_params = {
                        "lambda_over": lo,
                        "lambda_under": lu,
                        "theta_queue": tq
                    }

    print("✅ Best parameters found:")
    print(best_params)
    print(f"→ Total cost: {best_result['total_cash']:.2f}, avg price: {best_result['avg_price']:.4f}, shares: {best_result['filled']}")

    return best_params, best_result

# %% [markdown]
# ## Benchmarking the tuned parameters against baselines 

# %% [markdown]
# ### Take-the-best-ask strategy

# %%
def baseline_best_ask(snapshots, order_size=5000):
    remaining = order_size
    total_cash = 0.0
    filled = 0

    for snapshot in snapshots:
        if remaining <= 0:
            break

        #best venue from an ask price point of view
        best_venue = min(snapshot, key=lambda v: v['ask'])
        fill_qty = min(best_venue['ask_size'], remaining)

        total_cash += fill_qty * (best_venue['ask'] + best_venue['fee']) #how much we pay for this order
        filled += fill_qty
        remaining -= fill_qty

    avg_price = total_cash / filled if filled > 0 else float('inf')

    return {
        "total_cash": total_cash,
        "avg_price": avg_price
    }

# %% [markdown]
# ### 60-second-bucket TWAP

# %%
def baseline_twap(snapshots, order_size=5000):
    num_buckets = 9
    chunk_size = order_size // num_buckets
    remaining = order_size
    total_cash = 0.0
    filled = 0

    bucket_indices = np.linspace(0, len(snapshots)-1, num_buckets, dtype=int)

    for idx in bucket_indices:
        snapshot = snapshots[idx]
        shares_left = min(chunk_size, remaining)

        sorted_venues = sorted(snapshot, key=lambda v: v['ask'])
        for venue in sorted_venues:
            if shares_left <= 0:
                break
            fill_qty = min(venue['ask_size'], shares_left)
            if fill_qty == 0:
                continue  #skip venue with no liquidity
            total_cash += fill_qty * (venue['ask'] + venue['fee'])
            shares_left -= fill_qty
            remaining -= fill_qty
            filled += fill_qty
            

    avg_price = total_cash / filled
    return {"total_cash": total_cash, "avg_price": avg_price}


# %% [markdown]
# ### VWAP weighing prices by ask size

# %%
def baseline_vwap(snapshots, order_size=5000):
    remaining = order_size
    total_cash = 0.0
    filled = 0 

    for snapshot in snapshots:
        if remaining <= 0:
            break
        
        total_vol = sum(v['ask_size'] for v in snapshot)
        if total_vol == 0:
            continue

        for venue in snapshot:
            weight = venue['ask_size'] / total_vol
            desired_qty = int(weight * remaining)
            fill_qty = min(desired_qty, venue['ask_size'])
            if fill_qty == 0:
                continue  #skip venue with no liquidity
            total_cash += fill_qty * (venue['ask'] + venue['fee'])
            remaining -= fill_qty

            if remaining <= 0:
                break
            filled += fill_qty

    avg_price = total_cash / filled
    return {"total_cash": total_cash, "avg_price": avg_price}


# %% [markdown]
# ### Comparing our optimal model to the baselines

# %%
def bps_savings(base, tuned):
    return 10000 * (base - tuned) / base 

# %%
def compare_to_baselines(snapshots, best_params, best_result):
    best_ask = baseline_best_ask(snapshots)
    twap = baseline_twap(snapshots)
    vwap = baseline_vwap(snapshots)
    #how much we save with our tuned parameters compared to each baseline
    bps_best_ask = bps_savings(best_ask["avg_price"], best_result["avg_price"]) 
    bps_twap = bps_savings(twap["avg_price"], best_result["avg_price"])
    bps_vwap = bps_savings(vwap["avg_price"], best_result["avg_price"])
    
    output = {
        "best_params": best_params,
        "tuned_total_cost": best_result["total_cash"],
        "tuned_avg_price": best_result["avg_price"],
        "baseline_best_ask": {
            "total_cost": best_ask["total_cash"],
            "avg_price": best_ask["avg_price"]
        },
        "baseline_twap": {
            "total_cost": twap["total_cash"],
            "avg_price": twap["avg_price"]
        },
        "baseline_vwap": {
            "total_cost": vwap["total_cash"],
            "avg_price": vwap["avg_price"]
        },
        "savings_bps": {
            "best_ask": bps_best_ask,
            "twap": bps_twap,
            "vwap": bps_vwap
        }
    }

    print(json.dumps(output, indent=2))

# %%
snapshots = process_snapshots("l1_day.csv")

best_params, best_result = tune_parameters(snapshots)
compare_to_baselines(snapshots, best_params, best_result)

# %% [markdown]
# ## Plotting the cumulative cost of the router

# %%
def plot_cumulative_cost(snapshots, best_params):
    plt.figure(figsize=(10, 6))
    
    backtest = run_backtest(
        snapshots,
        lambda_over=best_params['lambda_over'],
        lambda_under=best_params['lambda_under'],
        theta_queue=best_params['theta_queue']
    )
    
    router_cost = backtest["cumulative_cost"]
    router_shares = backtest["shares_filled"]
    plt.plot(router_shares, router_cost)


    plt.title("Cumulative Cost Over Total Shares Bought")
    plt.xlabel("Total number of shares bought")
    plt.ylabel("Total Cash Spent ($)")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig("results.png")
    plt.show()

# %%
plot_cumulative_cost(snapshots, best_params)


