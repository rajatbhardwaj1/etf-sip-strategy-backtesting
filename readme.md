These are mainly for testing the SIP strategy, although test of lump-sum strategy is also there. User can run the funciton 
in the `main.py` and `main_non_SIP.py`.

Lets discuss the SIP strat, mainly the results, what is the best parameter to use this strat, how much returns one can expect,
does it beat nifty? below are the results. 

What I considered best parameters are as follows --

1. DMA = 10 , very important, for 20 its not giving as good results, at DMA = 10 , it beats nifty for 6y run easily. 
2. profit_thres = 6.5
3. trailing stoploss = 0.5
4. max buys = 1 
5. avg_down_thres = 0.4

I have assumed increment of 15% annually in the SIP.

I have compared the result of this strat with Nifty 50, i.e. at month end both strategy gets that lump sum , there are some
interesting observation, and tricks that lead to much better results ....... lets see 

We are using a hydration constant, i.e. if we run out of cash , we will supply from our pocket , without this hydration the strategy does 
not outperforms nifty for 2020-01-01 to 2025-09-28,

SIP amount = 50k 

| Hydration Constant | ETF SIP strat returns  | Nifty SIP returns |
|--------------------|------------------------|-------------------|
| 0                  | Row 1, Col 2           | Row 1, Col 3      |
| 100000             | Row 2, Col 2           | Row 2, Col 3      |
| 200000             | Row 2, Col 2           | Row 2, Col 3      |
| 400000             | Row 2, Col 2           | Row 2, Col 3      |
| 600000             | Row 2, Col 2           | Row 2, Col 3      |
| 1000000            | Row 2, Col 2           | Row 2, Col 3      |
    


SIP amount = 70k 

| Hydration Constant | ETF SIP strat returns  | Nifty SIP returns |
|--------------------|------------------------|-------------------|
| 0                  | Row 1, Col 2           | Row 1, Col 3      |
| 100000             | Row 2, Col 2           | Row 2, Col 3      |
| 200000             | Row 2, Col 2           | Row 2, Col 3      |
| 400000             | Row 2, Col 2           | Row 2, Col 3      |
| 600000             | Row 2, Col 2           | Row 2, Col 3      |
| 1000000            | Row 2, Col 2           | Row 2, Col 3      |
    