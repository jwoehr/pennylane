# Copyright 2018 Xanadu Quantum Technologies Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Tests for the QGT optimizer"""
import pytest

import pennylane as qml
from pennylane import numpy as np


class TestExceptions:
    """Test exceptions are raised for incorrect usage"""

    def test_obj_func_not_a_qnode(self):
        """Test that if the objective function is not a
        QNode, an error is raised."""

        dev = qml.device("default.qubit", wires=1)

        @qml.qnode(dev)
        def circuit(a):
            qml.RX(a, wires=0)
            return qml.expval(qml.PauliZ(0))

        def cost(a):
            return circuit(a)

        opt = qml.QGTOptimizer()
        params = 0.5

        with pytest.raises(ValueError, match="Objective function must be a QNode"):
            opt.step(cost, params)


class TestOptimize:
    """Test basic optimization integration"""

    def test_qubit_rotation(self):
        """Test qubit rotation has the correct QGT tensor
        after first step, and correct cost after 200 steps"""
        dev = qml.device("default.qubit", wires=1)

        @qml.qnode(dev)
        def circuit(params):
            qml.RX(params[0], wires=0)
            qml.RY(params[1], wires=0)
            return qml.expval(qml.PauliZ(0))

        eta = 0.01
        init_params = np.array([0.011, 0.012])
        num_steps = 200

        opt = qml.QGTOptimizer(eta)
        theta = init_params

        # optimization for 200 steps total
        for t in range(num_steps):
            theta = opt.step(circuit, theta)

            # check metric tensor
            res = opt.metric_tensor
            exp = [1 / 4, np.cos(theta[0]) ** 2 / 4]
            assert np.allclose(res, exp, atol=0.01, rtol=0)

        # check final cost
        assert np.allclose(circuit(theta), -0.9963791, atol=0.001, rtol=0)
