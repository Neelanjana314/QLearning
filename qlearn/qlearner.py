"""
This module defines the QLearner class that learns behaviour from a reward
matrix. The QLearer learns the action policy for the system by value
iteration using off-policy temporal difference learning to populate the value
matrix (Q-matrix) for each state/action pair.

    Value(state, action) = Q-Matrix[state, action]

    Policy(action | state) = max(Value(state, a) | a => all possible actions)

All learners expose the following interface:

* Instantiation with relevant parameters any any number of positional and
    keyword arguments.
* reward(state, action, next_state) which returns the reward for taking an
    action from some state.
* next_state(state, action) which returns the next state based on the current
    state and action.
* value(state) which returns the utility of a state and the following action
    what leads to that utility.
* learn() which runs over multiple episodes to populate a utility function
    or matrix.
* recommend(state) which recommends an action based on the learned values
    depending on the exploration vs. exploitation setting of the learner.
* reset() which returns the value function/matrix to its initial state while
    keeping any learning parameters provided at instantiation.
"""

import numpy as np
try:
    import utils
except ImportError:
    from . import utils


class QLearner:
    """
    A single-thread q learner with a reward matrix and goals that terminate the
    learning process.

    Args:
        rmatrix (ndarray/str): The reward matrix of [n states x m actions]. OR
            filepath to space delimited rmatrix file. Element [n, m] in the
            matrix represents the reward for taking action m from state n.
        goal (list/tuple/set/array/function): Indices of goal states in rmatrix
            OR a function that accepts a state index and returns true if goal.
        tmatrix (ndarray/str): A transition matrix of [n states x m actions], OR
            filepath to space delimited tmatrix. Where tmatrix[state, action]
            contains index of next state. If None, then rmatrix must be square
            of [n states x n states] i.e. no actions but direct state transitions.
        lrate (float): Learning rate for q-learning.
        discount (float): Discount factor for q-learning.
        exploration (float): Balance between exploring random states according
            to action selection policy, or exploiting already learned utilities
            to suggest max utility action. 1 means full exploration 0
            exploitation. 0.5 means half of each. Default is 0.
        policy (int): The action selection policy. Used durung learning/
            exploration to randomly select actions from a state. One of
            QLearner.[UNIFORM | GREEDY | SOFTMAX]. Default UNIFORM.
        mode (int): One of QLearner.[OFFLINE | ONLINE]. Offline updates action
            selection policy each learning episode. Online updates at every
            state/action inside the learning episode. Default OFFLINE (faster).
        seed (int): A seed for all random number generation in instance. Default
            is None.

    Instance Attributes:
        goal (func): Takes a state number (int) and returns bool whether it is
            a goal state or not.
        mode/policy/lrate/discount/exploration/rmatrix/tmatrix: Same as args.
        random (np.random.RandomState): A random number generator local to this
            instance.
    """

    UNIFORM = 0
    GREEDY = 1
    SOFTMAX = 2

    OFFLINE = 0
    ONLINE = 1

    def __init__(self, rmatrix, goal, tmatrix=None, lrate=0.25, discount=1,
                 exploration=0, policy=0, mode=0, seed=None, **kwargs):
        if seed is None:
            self.random = np.random.RandomState()
        else:
            self.random = np.random.RandomState(seed)

        self.qmatrix = None
        self.tmatrix = None
        self.rmatrix = None
        self._goals = set()
        self._next_state = None
        self._policy = None
        self.lrate = lrate
        self.discount = discount
        self.exploration = exploration
        self._action_param = {}   # helper parameter for GREEDY/SOFTMAX policies

        self.set_rq_matrix(rmatrix)
        self.set_transition_matrix(tmatrix)
        self.set_goal(goal)
        self.set_action_selection_policy(policy, mode, **kwargs)

    @property
    def num_states(self):
        """Returns number of states"""
        return len(self.rmatrix)

    @property
    def num_actions(self):
        """Returns number of possible actions"""
        return self.rmatrix.shape[1]


    def set_action_selection_policy(self, policy, mode=0, **kwargs):
        """
        Sets a policy for selecting subsequent actions while in a learning
        episode.

        Args:
            policy (int): One of QLearner.[UNIFORM | GREEDY | SOFTMAX].
            mode (int): One of QLearner.[OFFLINE | ONLINE]. Default OFFLINE.
            max_prob (float): Probability of choosing action with highest utility [0, 1).
        """
        self._action_param = {}
        self.mode = mode
        self.policy = policy
        if policy == QLearner.UNIFORM:
            self._policy = self._uniform_policy

        elif policy == QLearner.GREEDY:
            if 'max_prob' in kwargs:
                self._action_param['max_prob'] = kwargs['max_prob'] \
                                     - (1 - kwargs['max_prob']) / self.num_actions
                self._policy = self._greedy_policy
            else:
                raise KeyError('"max_prob" keyword argument needed for GREEDY policy.')

        elif policy == QLearner.SOFTMAX:
            self._policy = self._softmax_policy

        else:
            raise ValueError('Policy does not exist.')


    def set_rq_matrix(self, rmatrix):
        """
        Sets the reward/q-value matrices for the QLearner instance.

        Args:
            rmatrix (ndarray/str): The reward matrix of [n states x m actions].
                OR
                square matrix of [n states x n states] where each element is
                the reward for n->m transition.
                If string, then it is path to space delimited matrix file.
        """
        if isinstance(rmatrix, np.ndarray):
            self.rmatrix = rmatrix
        elif isinstance(rmatrix, str):
            self.rmatrix = utils.read_matrix(rmatrix)
        else:
            raise TypeError('Either provide filename or ndarray for R matrix.')
        self.qmatrix = np.ones_like(self.rmatrix)


    def set_goal(self, goal):
        """
        Sets a function that checks if a state is a goal state or not.

        Args:
            goal (list/tuple/set/array/function): Indices of goal states in
            rmatrix OR a function that accepts a state index and returns true if
            goal.
        """
        if isinstance(goal, (np.ndarray, list, tuple, set)):
            self._goals = set(goal)
            self.goal = lambda x: x in self._goals
        elif callable(goal):
            self._goals = set([g for g in range(self.num_states) if goal(g)])
            self.goal = goal
        else:
            raise TypeError('Provide goal as list/set/array/tuple/function.')


    def set_transition_matrix(self, tmatrix):
        """
        Sets the transition matrix in case of state-action-state transitions
        as opposed to state-state transitions (which only require a nxn matrix).

        Args:
            tmatrix (ndarray/str): A transition matrix of [n states x m actions]
                OR a filepath to the whitespace delimited tmatrix file.
            where tmatrix[state, action] contains index of next state.
        """
        if tmatrix is not None:
            if isinstance(tmatrix, str):    # if filepath, read file to matrix
                tmatrix = utils.read_matrix(tmatrix)
            elif not isinstance(tmatrix, np.ndarray): # if not filepath, must be array
                raise TypeError('tmatrix should be ndarray or filepath string.')
            if tmatrix.shape != self.rmatrix.shape:
                raise ValueError('Transition and R matrix must have same shape.')
            if tmatrix.dtype != int:
                raise TypeError('Transition matrix must have integer contents.')
            self.tmatrix = tmatrix
            self._next_state = lambda s, a: self.tmatrix[s, a]
        else:
            rows, cols = self.rmatrix.shape
            if rows != cols:
                raise ValueError('R matrix must be square if no transition matrix.')
            self._next_state = lambda s, a: a


    def episodes(self, coverage=1., mode=None):
        """
        Provides a sequence of states for learning episodes to start from.

        Args:
            coverage (float): Fraction of states to generate for episodes.
                Default= 1. Range [0, 1].
            mode (str): The order in which to loop through states. If 'bfs',
                performs a Breadth  First Search around goal states.
                Default=None (simply loops from 0 to number of states.

        Returns:
            A generator of of state indices.
        """
        num = int(self.num_states * coverage)
        if mode == 'bfs':
            enqueued = np.zeros(self.num_states, dtype=bool)
            queue = list(self._goals)
            enqueued[queue] = True
            i = 0
            # Do a BFS of the goal states' connected neighbourhood.
            while i < num and len(queue) > 0:
                i += 1
                state = queue.pop()
                for n in self.neighbours(state):
                    if not enqueued[n]:
                        enqueued[n] = True
                        queue.insert(0, n)
                yield state
            # If neighbourhoods of goal states are exhausted i.e. no more states
            # that can be accessed from goal states through any actions, then
            # generate the remainder by randomly picking from the unvisited
            # states:
            if i < num:
                choices = self.random.choice(np.arange(self.num_states)[enqueued],\
                                         size=num-i, replace=False)
                for j in range(num-i):
                    yield choices[j]
        else:
            for i in range(num):
                yield i


    def neighbours(self, state):
        """
        Returns a list/generator of state indices adjacent to provided state
        on the transition/reward matrix.

        Args:
            state (int): Index of state in [r|q] matrix.

        Returns:
            A list/generator of adjacent state indices. To be treated as a
            generator.
        """
        if self.tmatrix is None:
            return range(len(self.rmatrix))
        else:
            return self.tmatrix[state, :]


    def next_action(self, state):
        """
        Provides a sequence of actions based on the action selection policy.

        Args:
            state (int): Index of current state in [r|q]matrix.

        Returns:
            An index for the [q|r]matrix (column).
        """
        return self._policy(state)


    def next_state(self, state, action):
        """
        Returns the index of the next state based on the current state and
        action taken.

        Args:
            state (int): Index of current state in [r|q]matrix.
            action (int): Index of action taken in [r|q]matrix.

        Returns:
            int representing index of next state in [r|q] matrix.
        """
        return self._next_state(state, action)


    def reward(self, cstate, action, nstate):
        """
        Returns the reward of taking action from state.

        Args:
            cstate (int): Index of current state in [r|q]matrix (row index).
            action (int): Index of action to be taken from state (column index).
            nstate (int): Index of next state in [r|q]matrix.

        Returns:
            A float indicating the reward.
        """
        return self.rmatrix[cstate, action]


    def value(self, state):
        """
        The mean utility of all actions from the state.

        Args:
            state (int): Index of current state in [r|q]matrix (row index).

        Returns:
            A tuple of a float representing the value(state) and the action index
            for the most rewarding next action.
        """
        action = np.argmax(self.qmatrix[state, :])
        return (self.qmatrix[state, action], action)


    def utility(self, state, action):
        """
        Computes the utility of a proposed action from a state based on
        temporal difference learning.

        Args:
            state (int): Index of current state in [r|q]matrix (row index).
            action (int): Index of action to be taken from state (column index).

        Returns:
            A tuple of a float containing the updated utility for
            qmatrix(state, action) and the next state.
        """
        next_state = self.next_state(state, action)
        return (self.qmatrix[state, action] \
                + self.lrate*(self.reward(state, action, next_state)
                              + self.discount*np.max(self.qmatrix[next_state])
                              - self.qmatrix[state, action]),
                next_state)


    def learn(self, coverage=1., ep_mode=None):
        """
        Begins learning procedure over all (state, action) pairs. Populates the
        Q matrix with utility for each (state, action).

        Args:
            coverage (float): Fraction of total states to start episodes from.
                Default=1 i.e. all state are covered by episodes().
            ep_mode (str): Order in which to iterate through states. See
                episodes() mode argument.
        """
        num_states = self.qmatrix.shape[0]
        for state in self.episodes(coverage=coverage, mode=ep_mode):
            limit = 0
            if self.mode == QLearner.OFFLINE:
                self._update_policy()
            # The limit variable keeps the number of iterations in check. They
            # should not exceed the number of states in the system.
            while not self.goal(state) and limit < num_states:
                limit += 1
                action = self.next_action(state)
                self.qmatrix[state, action], state = self.utility(state, action)


    def recommend(self, state):
        """
        Recommends an action based on the learned q matrix and current state.
        Must be called after learn(). Either recommends an exploratory action
        or an action with the highest utility according to self.exploration
        setting (1 to 0).

        Args:
            state (int): Index of current state in [r|q]matrix.

        Returns:
            Index of action to take (column) in [r|q]matrix.
        """
        if self.random.rand() < self.exploration:
            # explore
            action = self.next_action(state)
            self.qmatrix[state, action], _ = self.utility(state, action)
            return action
        else:
            # exploit
            return np.argmax(self.qmatrix[state])


    def reset(self):
        """
        Resets self.qmatrix to initial state. This is useful in case the same
        QLearner instance is being used again for learning using a different
        policy or mode.
        The qmatrix is not automatically reset for each learn() call to allow
        for the learning process to build upon a custom qmatrix provided.
        """
        self.qmatrix = np.ones_like(self.rmatrix)


    def _uniform_policy(self, state):
        """
        Selects an action based on a uniform probability distribution.

        Args:
            state (int): Index of current state.

        Returns:
            Index of action in [r|q]matrix.
        """
        return self.random.randint(self.num_actions)


    def _greedy_policy(self, state):
        """
        Select highest utility action with higher probability. Others are
        uniformly selected.

        Args:
            state (int): Index of current state.

        Returns:
            Index of action in [r|q]matrix.
        """
        if self.mode == QLearner.ONLINE:
            if self.random.uniform() < self._action_param['max_prob']:
                return np.argmax(self.qmatrix[state])
            else:
                return self.random.randint(self.num_actions)
        elif self.mode == QLearner.OFFLINE:
            if self.random.uniform() < self._action_param['max_prob']:
                return self._action_param['max_util_indices'][state]
            else:
                return self.random.randint(self.num_actions)


    def _softmax_policy(self, state):
        """
        Selects actions with probability proportional to their utility in
        qmatrix[state,:]

        Args:
            state (int): Index of current state.

        Returns:
            Index of action in [r|q]matrix.
        """
        if self.mode == QLearner.ONLINE:
            cumulative_utils = np.cumsum(self.qmatrix[state])
            random_num = self.random.rand() * cumulative_utils[-1]
            return np.searchsorted(cumulative_utils, random_num)
        elif self.mode == QLearner.OFFLINE:
            random_num = self.random.rand()  \
                        * self._action_param['cumulative_utils'][state][-1]
            ind = np.searchsorted(self._action_param['cumulative_utils'][state],\
                                random_num)
            # Searchsorted returns size of array if number is larger than
            # largest element. The conditional return addresses that.
            return ind if ind < self.qmatrix.shape[1] else ind - 1


    def _update_policy(self):
        """
        Updates OFFLINE [SOFTMAX | GREEDY] policy every episode by updating
        how new actions are suggested based on current utility.
        """
        if self.policy == QLearner.GREEDY:
            # max_util_indices is a list of action indices (column #s) with the
            # highest q value for each state. Used to generate random numbers
            # based on the greedy policy.
            self._action_param['max_util_indices'] = np.argmax(self.qmatrix, axis=1)
        elif self.policy == QLearner.SOFTMAX:
            # cumulative_utils is the cumulative sum of the action q values for
            # each state. This is used to generate a random number based on the
            # relative utility of each action in a state.
            self._action_param['cumulative_utils'] = np.cumsum(self.qmatrix, axis=1)
