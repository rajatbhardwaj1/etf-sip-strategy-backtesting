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

 We are using a SIP of 30,000 INR. End date is fixed at 1 Oct 2025. XIRR values for ETF strategy and Nifty are shown. We are using hydration constant of 1,00,000

| Start Date | End Date    | ETF SIP Strategy XIRR | Nifty SIP XIRR |
|------------|------------|-----------------------|----------------|
| 2020-01-01 | 2025-10-01 | 21.8%                 | 12.63%         |
| 2021-01-01 | 2025-10-01 | 21.26%                | 10.55%         |
| 2022-01-01 | 2025-10-01 | 18.66%                | 10.24%         |
| 2023-01-01 | 2025-10-01 | 15.4%                 | 9.3%           |
| 2024-01-01 | 2025-10-01 | 13.41%                | 4.39%          |
| 2025-01-01 | 2025-10-01 | 9.60%                 | 6.70%          |
| 2025-04-01 | 2025-10-01 | 3.16%                 | 2.57%          |
| 2025-06-01 | 2025-10-01 | -0.62%                | -3.83%         |
| 2025-08-01 | 2025-10-01 | 1.54%                 | 1.95%          |


