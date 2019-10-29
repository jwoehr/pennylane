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
r"""
Experimental simulator plugin based on tensor network contractions
"""
import functools

import numpy as np
import tensornetwork as tn

from pennylane.utils import _flatten
from pennylane import Device
from pennylane.plugins.default_qubit import I, X, Y, Z, H, CNOT, SWAP, CZ, S, T, CSWAP, \
    Rphi, Rotx, Roty, Rotz, Rot3, CRot3, CRotx, CRoty, CRotz, CRot3, hermitian, identity, \
    unitary

# tolerance for numerical errors
tolerance = 1e-10

#========================================================
#  device
#========================================================


class TensorNetwork(Device):
    """Experimental Tensor Network simulator device for PennyLane.

    Args:
        wires (int): the number of modes to initialize the device in
    """
    name = 'PennyLane TensorNetwork simulator plugin'
    short_name = 'expt.tensornet'
    pennylane_requires = '0.7'
    version = '0.7.0'
    author = 'Xanadu Inc.'
    _capabilities = {"model": "qubit", "tensor_observables": True}

    _operation_map = {
        'QubitStateVector': None,
        'BasisState': None,
        'QubitUnitary': unitary,
        'PauliX': X,
        'PauliY': Y,
        'PauliZ': Z,
        'Hadamard': H,
        'S': S,
        'T': T,
        'CNOT': CNOT,
        'SWAP': SWAP,
        'CSWAP':CSWAP,
        'CZ': CZ,
        'PhaseShift': Rphi,
        'RX': Rotx,
        'RY': Roty,
        'RZ': Rotz,
        'Rot': Rot3,
        'CRX': CRotx,
        'CRY': CRoty,
        'CRZ': CRotz,
        'CRot': CRot3
    }

    _observable_map = {
        'PauliX': X,
        'PauliY': Y,
        'PauliZ': Z,
        'Hadamard': H,
        'Hermitian': hermitian,
        'Identity': identity
    }

    def __init__(self, wires):
        super().__init__(wires, shots=1)
        self.eng = None
        self.analytic = True
        self._nodes = []
        self._edges = []
        self._zero_state = np.zeros([2] * wires)
        self._zero_state[tuple([0] * wires)] = 1.0
        self._input_state_node = self._add_node(self._zero_state, wires=tuple(w for w in range(wires)), name="AllZeroState")

    def _add_node(self, A, wires, name="UnnamedNode"):
        name = "{}{}".format(name, tuple(w for w in wires))
        if isinstance(A, tn.Node):
            A.set_name(name)
            node = A
        else:
            node = tn.Node(A, name=name)
        self._nodes.append(node)
        return node

    def _add_edge(self, node1, idx1, node2, idx2):
        edge = tn.connect(node1[idx1], node2[idx2])
        self._edges.append(edge)
        return edge

    def _permute(self, axes):
        """Permute a set of indices from (i1, i2, i3,..., j1, j2, j3,...) ordering to (i1, j1, i2, j3, ...) ordering."""
        p = []
        for idx in range(len(axes) // 2):
            p += [axes[idx], axes[len(axes)//2 + idx]]
        #return p
        return axes[::2] + axes[1::2]

    def _reshape(self, A, num_axes, order='C'):
        A = np.reshape(A, [2] * num_axes, order=order)
        A = np.transpose(A, axes=self._permute([idx for idx in range(num_axes)]))
        return A

    def pre_apply(self):
        self.reset()

    def apply(self, operation, wires, par):
        A = self._get_operator_matrix(operation, par)
        num_mult_idxs = len(wires)
        A = self._reshape(A, num_mult_idxs * 2)
        op_node = self._add_node(A, wires=wires, name=operation)
        output_edge_order = self._state.edges  # tensornetwork needs this info to preserve edge order
        for idx, w in enumerate(wires):
            # TODO: confirm "right-multiplication" indices for tensor A
            self._add_edge(op_node, num_mult_idxs + idx, self._state, w)
            output_edge_order[idx] = op_node[idx]
        # TODO: can be smarter here about collecting contractions?
        self._state = tn.contract_between(op_node, self._state, output_edge_order=output_edge_order)
        print(self._state._tensor.reshape(-1))
        print("\n")

    def expval(self, observable, wires, par):
        if not isinstance(observable, list):
            observable = [observable]
            wires = [wires]
            par = [par]
        matrices = []
        for o, p, w in zip(observable, par, wires):
            A = self._get_operator_matrix(o, p)
            num_mult_idxs = len(w)
            matrices.append(self._reshape(A, num_mult_idxs * 2))
        nodes = [self._add_node(A, w, name=o) for A, w, o in zip(matrices, wires, observable)]
        return self.ev(nodes, wires)

    def _get_operator_matrix(self, operation, par):
        """Get the operator matrix for a given operation or observable.

        Args:
          operation    (str): name of the operation/observable
          par (tuple[float]): parameter values
        Returns:
          array: matrix representation.
        """
        A = {**self._operation_map, **self._observable_map}[operation]
        if not callable(A):
            return A
        return A(*par)

    def ev(self, obs_nodes, wires):
        r"""Expectation value of observables on specified wires.

         Args:
            obs_nodes (tn.Node): the observables as tensornetwork Nodes
            wires (Sequence[int]): measured subsystems for each observable
         Returns:
            float: expectation value :math:`\expect{A} = \bra{\psi}A\ket{\psi}`
        """
        # first need to connect together nodes representing measurement
        all_wires = tuple(w for w in range(self.num_wires))
        ket = self._add_node(self._state, wires=all_wires, name="Ket")
        bra = self._add_node(tn.conj(ket), wires=all_wires, name="Bra")
        meas_wires = []
        for obs_node, obs_wires in zip(obs_nodes, wires):
            meas_wires.extend(obs_wires)
            for idx, w in enumerate(obs_wires):
                left_mult_index = idx
                right_mult_index = len(obs_wires) + idx
                self._add_edge(obs_node, right_mult_index, ket, w)  # A|psi>
                self._add_edge(bra, w, obs_node, left_mult_index)  # <psi|A
        for w in set(all_wires) - set(meas_wires):
            self._add_edge(bra, w, ket, w)  # |psi[w]|**2

        # contractions
        contracted_ket = ket
        for obs_node in obs_nodes:
            contracted_ket = tn.contract_between(obs_node, contracted_ket)
        expval = tn.contract_between(bra, contracted_ket).tensor
        if np.abs(expval.imag) > tolerance:
            warnings.warn('Nonvanishing imaginary part {} in expectation value.'.format(expval.imag), RuntimeWarning)
        return expval.real

    def reset(self):
        """Reset the device"""
        self._state = self._input_state_node

    @property
    def operations(self):
        return set(self._operation_map.keys())

    @property
    def observables(self):
        return set(self._observable_map.keys())

