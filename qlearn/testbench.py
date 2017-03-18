"""
This module creates a testbench for the learning algorithm which illustrates
its progress graphically. The problem is a tolopogy where the objective is to
get to the lowest altitude possible.
"""

import numpy as np
from mpl_toolkits.mplot3d import Axes3D
import matplotlib.pyplot as plt
from qlearner import QLearner
from tb_utils import abs_cartesian
from tb_utils import fault_algorithm



class TestBench:
    """
    The testbench class simulates the learning procedure implemented by the
    Qlearner class graphically for illustration. It generates a geographical
    system - a square grid where each point has a height. The goal states are
    coordinates with lower heights. Possible actions/transitions are movements
    to adjacent points. There are two state variables: x and y coords. Each
    instance automatically generates transition and reward matrices that can
    be used by a QLearner instance.

    Args:
        size (int): The size of each side of the topology (size * size points).
        seed (int): The seed for the random number generator.
        method (str): Method for generating topology. Default='fault'.
        goals (int/list): Number of goal states. Default = size. If list, then
            (y, x) coordinates of goal states in topology.
        wrap (bool): Whether or not the topology wraps at edges. Default=False.
        qlearner (QLearner): QLearner instance which has called learn(). Defaults
            to None in which case a Qlearner instance with default arguments is
            generated with any extra keyword arguments passed on.
        **kwargs: A sequence of keyword arguments to instantiate the qlearner
            if one is not provided. Any keywords except tmatrix, rmatrix, and
            goals which are provided by the TestBench.

    Instance Attributes:
        topology (2D ndarray): A square array of heights defining the system.
            Heights are stored as [y, x] coordinates in line with the array
            indexing convention.
        size (int): Size of topology (length of side).
        states (int): Number of possible states/positions in the system.
        actions (2D ndarray): An array where each row defines an action by a
            change in topology coordinates. For e.g. [1,0] is move-up.
        path (list): Sequence of coordinates (y, x) tuples taken on topology to
            reach goal state. Populated by episode() function.
        tmatrix (2D ndarray): The transition matrix.
        rmatrix (2D ndarray): The reward matrix.
        goals (list): List of goal state numbers (coords encoded into int).
        num_goals (int): Number of goal states.
        qlearner (QLearner): QLearner instance. The learn() function must be
            called before visualizing the learned policy function.
        fig (plt.figure): A matplotlib figure instance storing all plots.
        topo_ax (Axes3D): An axis object storing the 3D plots.
        topo_surface (Poly3DCollection): Contains plotted surface.
        path_line (list): Stores a list of lists of all Line3D segments plotted
            on the figure. Populated after show_topology(). path_line[0] will
            be a list of Line3D instances representing the first line and so on.
    """

    plot_num = -1

    def __init__(self, size=10, seed=0, method='fault', goals=None, wrap=False,
                 qlearner=None, **kwargs):
        np.random.seed(seed)
        # qlearning params
        self.topology = np.zeros((size, size))
        self.size = size
        self.states = size * size
        self.actions = np.array([[1, 0], [0, 1], [-1, 0], [0, -1]])
        self.path = []
        self.tmatrix = np.array([])
        self.rmatrix = np.array([])
        if isinstance(goals, (int, float)):
            self.goals = []
            self.num_goals = abs(int(goals))
        elif isinstance(goals, (list, tuple, np.ndarray)):
            goals = [self.coord2state(g) for g in goals]
            self.goals = [g for g in goals if g >= 0 and g < self.states]
            self.num_goals = len(self.goals)
        else:
            self.goals = []
            self.num_goals = self.size
        self.qlearner = qlearner

        # plotting variables
        self.__class__.plot_num += 1
        self.fig_num = self.__class__.plot_num
        self.fig = None
        self.topo_ax = None
        self.topo_surface = None
        self.path_line = None

        self.create_topology(method)
        self.generate_trg(wrap)
        if self.qlearner is None:
            self.qlearner = QLearner(self.rmatrix, self.goals, self.tmatrix, \
                            **kwargs)


    def episode(self, start=None, interactive=True, limit=-1):
        """
        Run a single episode from the provided qlearner. The episode starts at
        coordinates 'start' and ends when it reaches a goal state. Calls the
        self.qlearner.recommend() function to get sequence of actions to take
        based on the learned Q-Matrix.

        Args:
            start (list/tuple/ndarray): y and x coordinates to start from. If
                None, generates random coordinates. Of the form (y, x).
            interactive (bool): If true, shows the plot. Else returns a list
                of coordinates (y,x) traversed on path.
            limit (int): Maximum number of steps in episode before quitting.
                Defaults to self.size*self.size.

        Return:
            A list of coordinates stored in self.path that were traversed to
            reach the goal state. Only when interactive=False.
        """
        if start is None:
            start = (np.random.randint(self.size), np.random.randint(self.size))
        self.path = [tuple(start)]
        limit = self.size**2 if limit <= 0 else limit
        current = self.coord2state(start)
        iteration = 0
        while current not in self.goals and iteration < limit:
            iteration += 1
            action = self.qlearner.recommend(current)
            current = self.tmatrix[current, action]
            self.path.append(self.state2coord(current))
        if interactive:
            self.show_topology(QPath=self.path)
        else:
            return self.path


    def shortest_path(self, point, metric=abs_cartesian):
        """
        Returns the shortest path between the point and any of the goal states
        where the distance between two adjacent states/points is determined by
        the metric. Uses Dijkstra's algorithm.

        Args:
            point (tuple/list/ndarray): (y, x) coordinates of point.
            metric (func): A function that calculates the measure of distance
                between two points on the topology. Signature is:
                    func(topology, source, target)
                Where topology is self.topology, source is the source point,
                and target is the point to which the distance is measured.
                All points are (y, x) coordinates. Returns a positive float.

        Returns:
            A list containing the optimal path from the point to one of the
            goal states. The list contains points on the topology (y, x)
            traversed.
        """
        # Set up initial distances, visited status, and target states.
        # All states intially loop back to themselves.
        distances = np.array([(i, np.inf) for i in range(self.states)])
        distances[self.coord2state(point)][1] = 0
        predecessors = np.arange(self.states)
        unvisited = np.ones(self.states, dtype=bool)
        goals_left = set(self.goals)

        # Explore closest state from source as long as there are targets/states left
        while len(goals_left):
            closest = int(distances[unvisited][np.argmin(distances[unvisited], axis=0)[1]][0])
            unvisited[closest] = False
            if closest in goals_left:
                goals_left.remove(closest)

            neighbours = [n for n in self.tmatrix[closest, :] if unvisited[n]]
            for n in neighbours:
                distance = metric(self.topology, self.state2coord(closest),\
                                self.state2coord(n))
                if distance < distances[n, 1]:
                    distances[n, 1] = distances[closest, 1] + distance
                    predecessors[n] = closest

        # Find closest goal state and trace path back to source
        goal_distances = distances[self.goals, 1]
        closest_goal = self.goals[np.argmin(goal_distances)]
        path = [self.state2coord(closest_goal)]
        state = closest_goal
        prev = predecessors[state]
        while prev != state:
            path.insert(0, self.state2coord(prev))
            state = prev
            prev = predecessors[state]
        # Check if last element in path is goal state
        if path[-1] != self.state2coord(closest_goal):
            raise ValueError('Shortest path could not be found.')
        elif path[0] != tuple(point):
            raise ValueError('Could not trace goal to starting point.')
        return path


    def show_topology(self, **paths):
        """
        Draws a surface plot of the topology, marks goal states, and any episode
        up to its current progress.

        Args:
            **paths: A sequence of keyword arguments describing paths to plot
                on the topology. They should be of the form:
                <PATH_NAME>=[LIST OF (y, x) COORDINATE PAIRS]
        """
        self.fig = plt.figure(self.fig_num)
        self.topo_ax = self.fig.add_subplot(111, projection='3d')
        self.path_line = []
        self.topo_ax.invert_yaxis()
        # Plot 3d topology surface
        x, y = np.meshgrid(np.linspace(0, self.size-1, self.size),\
                            np.linspace(0, self.size-1, self.size))
        z = self.topology.reshape(x.shape)
        self.topo_surface = self.topo_ax.plot_surface(x, y, z, cmap='gist_earth')
        # Plot goal states
        gc = [self.state2coord(i) for i in self.goals]  # goal coords
        gz = [self.topology[g[0], g[1]] for g in gc]
        gx = [g[1] for g in gc]
        gy = [g[0] for g in gc]
        self.topo_ax.scatter(gx, gy, gz)
        # Plot path
        for path, coords in paths.items():
            px = [p[1] for p in coords]
            py = [p[0] for p in coords]
            pz = [self.topology[p[0], p[1]] for p in coords]
            self.path_line.append(self.topo_ax.plot(px, py, pz, label=path))
        # Set labels
        self.topo_ax.set_xlabel('X')
        self.topo_ax.set_ylabel('Y')
        self.topo_ax.set_zlabel('Altitude')
        if len(paths) > 0:
            plt.legend()
        # Display figure
        plt.show(block=True)
        self.fig.clear()
        plt.close(self.fig_num)


    def create_topology(self, method='fault', *args, **kwargs):
        """
        Creates a square height map based on one of several terrain generation
        algorithms. The topology is stored in self.topology (2D ndarray), where
        self.topology[y, x] = height at coordinate (x, y).

        Args:
            method (str/func): The algorithm to use. Default='fault'. OR it can
                also be a function object. The function must populate self.topolgy
                with values of heights at (y, x) coordinates. The function must
                take this TestBench instance as its first argument. Signature
                like:
                    function(self, *args, **kwargs)
            *args: Positional arguments passed on to method if it is a function.
            **kwargs: Keyword arguments passed on to method if it is a function.
        """
        if callable(method):
            method(self, *args, **kwargs)
        elif method == 'fault':
            self.topology = fault_algorithm(int(np.random.rand() * 200),\
                            (self.size, self.size))


    def generate_trg(self, wrap=False):
        """
        Calculates goal states and creates transition & reward matrices. Where
        tmatrix[state, action] points to index of next state. And
        rmatrix[state, action] is the reward for taking that action. State is
        he encoded state number from coords2state. The transitions roll over:
        i.e going right from the right-most coordinate takes to the left-most
        coordinate.

        Args:
            wrap (bool): Whether or not the topology wraps around boundaries.
                Default = False.
        """
        tmatrix = np.zeros((self.states, len(self.actions)), dtype=int)
        rmatrix = np.zeros((self.states, len(self.actions)))
        # updating goal states
        goal_state = np.argsort(np.ravel(self.topology))[:self.num_goals]

        for i in range(self.states):
            coords = self.state2coord(i)
            # updating r and t matrices
            for j, action in enumerate(self.actions):
                next_coord = coords + action
                if wrap:
                    next_coord[next_coord < 0] += self.size
                    next_coord[next_coord >= self.size] -= self.size
                else:
                    next_coord[next_coord < 0] = 0
                    next_coord[next_coord >= self.size] = self.size - 1
                tmatrix[i, j] = self.coord2state(next_coord)

                rmatrix[i, j] = self.topology[coords[0], coords[1]] \
                                - self.topology[next_coord[0], next_coord[1]]
        self.tmatrix = tmatrix
        self.rmatrix = rmatrix
        if len(self.goals) == 0:
            self.goals = goal_state


    def coord2state(self, coord):
        """
        Encodes coordinates into a state number that can be used as an index.
        Essentially converts Base_size coordinates into Base_10.

        Args:
            coord (tuple/list/ndarray): 2 coordinates [row, column]

        Returns:
            An integer representing coordinates.
        """
        return int(self.size * coord[0] + coord[1])


    def state2coord(self, state):
        """
        Converts a state number into two coordinates. Essentially converts
        Base_10 state into Base_size coordinates.

        Args:
            state (int): An integer representing a state.

        Returns:
            A 2 element tuple of [row, column] coordinates.
        """
        return (int(state/self.size) % self.size, state % self.size)
