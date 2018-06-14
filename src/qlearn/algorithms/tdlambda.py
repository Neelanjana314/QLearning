"""
Implements the multi-step q-learning algorithm, known as TD(lambda) for a single
episode.
"""
from typing import List

import numpy as np

from ..agent.spaces import to_space, to_tuple


def tdlambda(agent: 'Agent', discount: float, steps: int=0) -> List[float]:
    """
    Off-policy temporal difference learning with delayed rewards. Extension
    of qlearning `q` algorithm with muiti-step loopahead. Uses value
    iteration to learn policy. Value function is incrementaly learned. New
    estimate of value (`V'`) is (`d`=discount, `r`=reward):

        `V'(s, a) = r + d * max_{a'}V(s', a') + d^2 * max_{a''}V(s'', a'') + ...`

    Note: Temporal difference methods with off-policy and non-tabular value
    function approximations may not converge [4.2 Ch. 11.3 - Deadly Triad].

    Args:
    * agent: The agent calling the learning function.
    * discount: The discount level for future rewards. Between 0 and 1.
    * steps: The number of steps to accumulate reward.
    """
    # Illustration of various TD methods at timestep 't'. tau is the state whose
    # value is updated. t is the current timestep of the episode.
    # s0  s1  s2  s3  s4  s5  s6  s7
    # a0  a1  a2  a3  a4  a5  a6        a0 is action from s0 -> s1
    # r0  r1  r2  r3  r4  r5  r6        r0 is reward from a0
    # 0   1   2   3   4   5   t  t+1
    #        tau  -   -   -   -         TD(4) - current + delayed rewards
    #                tau  -   -         TD(2) - current + delayed rewards
    #                        tau        TD(0) - only current reward
    states = [to_tuple(agent.env.observation_space, agent.env.reset())]
    actions = []    # history of actions in episode
    rewards = []    # history of rewards for actions
    returns = []    # contains returns as new estimates of value to be learned
    done = False
    T = np.inf      # termination time (i.e. terminal state)
    tau = 0         # time of state being updated
    t = 0           # time from beginning of episode i.e current timestep

    # update states until penultimate state. No action is taken from the final
    # state, therefore there is no reward to consider.
    while tau < T - 1:
        # Observe new states until episode ends.
        if t < T:
            state = states[-1]
            action = agent.next_action(state)    # select exploratory action
            actions.append(action)               # store history of actions
            # Observe next state and rewards
            nstate, reward, done, _ = agent.env.step(to_space(agent.env.action_space, action))
            nstate = to_tuple(agent.env.observation_space, nstate)
            states.append(nstate)    # store history of states
            rewards.append(reward)   # accumulate rewards for aggregation
            if done:
                T = t + 1
                # If episode ends before sufficient delayed rewards, salvage
                # whatever rewards have accumulated so far.
                if T < steps:
                    steps = t

        # If the episode has proceeded far enough (t >= steps), start estimating
        # returns for states observed earlier.
        tau = t - steps
        if tau >= 0:
            ret, k = 0., 0
            for k in range(tau, min(tau + steps + 1, T)):
                ret += discount**k * rewards[k]
            nvalue, _ = agent.maximum(states[k+1])
            ret += discount**(k+1) * nvalue
            # update value function with new estimate
            returns.append(ret)
            agent.value.update(((*states[tau], *actions[tau]),), (ret,))
        t += 1
    return rewards