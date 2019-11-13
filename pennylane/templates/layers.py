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
Layers are trainable templates that are typically repeated, using different adjustable parameters in each repetition.
They implement a transformation from a quantum state to another quantum state.
"""
#pylint: disable-msg=too-many-branches,too-many-arguments,protected-access
from pennylane import numpy as np
from pennylane.ops import CNOT, RX, RY, RZ, Rot, Squeezing, Displacement, Kerr
from pennylane.templates.subroutines import Interferometer
from pennylane.templates.utils import (_check_shape, _check_no_variable, _check_wires,
                                       _check_type)


def _strongly_entangling_layer(weights, wires, r, imprimitive):
    r"""A layer applying rotations on each qubit followed by cascades of 2-qubit entangling gates.

    Args:
        weights (array[float]): array of weights of shape ``(len(wires), 3)``
        wires (Sequence[int]): sequence of qubit indices that the template acts on
        r (int): range of the imprimitive gates of this layer, defaults to 1
        imprimitive (pennylane.ops.Operation): two-qubit gate to use, defaults to :class:`~pennylane.ops.CNOT`
    """

    for i, wire in enumerate(wires):
        Rot(weights[i, 0], weights[i, 1], weights[i, 2], wires=wire)

    n_wires = len(wires)
    if n_wires > 1:
        for i in range(n_wires):
            imprimitive(wires=[wires[i], wires[(i + r) % n_wires]])


def _random_layer(weights, wires, ratio_imprim, imprimitive, n_rots, rotations, seed):
    r"""A single random layer.

    Args:
        weights (array[float]): array of weights of shape ``(k,)``
        wires (Sequence[int]): sequence of qubit indices that the template acts on
        ratio_imprim (float): value between 0 and 1 that determines the ratio of imprimitive to rotation gates
        imprimitive (pennylane.ops.Operation): two-qubit gate to use, defaults to :class:`~pennylane.ops.CNOT`
        n_rots (int): number of rotations per layer
        rotations (list[pennylane.ops.Operation]): List of Pauli-X, Pauli-Y and/or Pauli-Z gates. The frequency
            determines how often a particular rotation type is used. Defaults to the use of all three
            rotations with equal frequency.
        seed (int): seed to generate random architecture
    """
    if seed is not None:
        np.random.seed(seed)

    i = 0
    while i < n_rots:
        if np.random.random() > ratio_imprim:
            gate = np.random.choice(rotations)
            wire = np.random.choice(wires)
            gate(weights[i], wires=wire)
            i += 1
        else:
            if len(wires) > 1:
                on_wires = np.random.permutation(wires)[:2]
                on_wires = list(on_wires)
                imprimitive(wires=on_wires)


def _cv_neural_net_layer(theta_1, phi_1, varphi_1, r, phi_r, theta_2, phi_2, varphi_2, a, phi_a, k, wires):
    r"""A single continuous-variable neural network layer.

    The layer acts on the :math:`M` wires modes specified in ``wires``, and includes interferometers
    of :math:`K=M(M-1)/2` beamsplitters.

    Args:
        theta_1 (array[float]): length :math:`(K, )` array of transmittivity angles for first interferometer
        phi_1 (array[float]): length :math:`(K, )` array of phase angles for first interferometer
        varphi_1 (array[float]): length :math:`(M, )` array of rotation angles to apply after first interferometer
        r (array[float]): length :math:`(M, )` array of squeezing amounts for
            :class:`~pennylane.ops.Squeezing` operations
        phi_r (array[float]): length :math:`(M, )` array of squeezing angles for
            :class:`~pennylane.ops.Squeezing` operations
        theta_2 (array[float]): length :math:`(K, )` array of transmittivity angles for second interferometer
        phi_2 (array[float]): length :math:`(K, )` array of phase angles for second interferometer
        varphi_2 (array[float]): length :math:`(M, )` array of rotation angles to apply after second interferometer
        a (array[float]): length :math:`(M, )` array of displacement magnitudes for
            :class:`~pennylane.ops.Displacement` operations
        phi_a (array[float]): length :math:`(M, )` array of displacement angles for
            :class:`~pennylane.ops.Displacement` operations
        k (array[float]): length :math:`(M, )` array of kerr parameters for :class:`~pennylane.ops.Kerr` operations
        wires (Sequence[int]): sequence of mode indices that the template acts on
    """
    Interferometer(theta=theta_1, phi=phi_1, varphi=varphi_1, wires=wires)
    for i, wire in enumerate(wires):
        Squeezing(r[i], phi_r[i], wires=wire)

    Interferometer(theta=theta_2, phi=phi_2, varphi=varphi_2, wires=wires)

    for i, wire in enumerate(wires):
        Displacement(a[i], phi_a[i], wires=wire)

    for i, wire in enumerate(wires):
        Kerr(k[i], wires=wire)


def StronglyEntanglingLayers(weights, wires, repeat=1, ranges=None, imprimitive=CNOT):
    r"""Layers of type :func:`StronglyEntanglingLayer()`, consisting of single qubit rotations and entanglers,
     [inspired by `arXiv:1804.00633 <https://arxiv.org/abs/1804.00633>`_].

    The first dimension of ``weights`` indicates the number of times a layer architecture
    is repeated and has to be equal to ``repeat``.

    The 2-qubit gates, whose type is specified by the ``imprimitive`` argument,
    act chronologically on the wires with their first qubit, while the second qubit is
    determined by a hyperparameter :math:`r` called the *range* (which indicates how many wires in a
    linear chain of qubits lie between the two). If the first qubit is :math:`i`, the second qubit is
    :math:`(i+r)\mod n`, where :math:`n` is the total number of wires in the template.

    If applied to one qubit only, this template will use no imprimitive gates.

    This is an example of two 4-qubit strongly entangling layers (ranges :math:`r=1` and :math:`r=2`, respectively) with
    rotations :math:`R` and CNOTs as imprimitives:

    .. figure:: ../../_static/layer_sec.png
        :align: center
        :width: 60%
        :target: javascript:void(0);

    Args:
        weights (array[float]): array of weights of shape ``(repeat, len(wires), 3)``
        wires (Sequence[int] or int): int or sequence of qubit indices that the template acts on

    Keyword Args:
        repeat (int): number of layers applied
        ranges (Sequence[int]): sequence determining the range hyperparameter for each subsequent layer

        imprimitive (pennylane.ops.Operation): two-qubit gate to use, defaults to :class:`~pennylane.ops.CNOT`

    Raises:
        ValueError if arguments do not have the correct format.
    """
    if ranges is None:
        ranges = [1] * repeat

    #############
    # Input checks
    _check_no_variable([repeat, ranges, imprimitive], ['repeat', 'ranges', 'imprimitive'])
    wires, n_wires = _check_wires(wires)
    _check_shape(weights, (repeat, n_wires, 3))
    _check_type(repeat, [int])
    _check_type(ranges, [list])
    _check_type(ranges[0], [int])
    ###############

    for l in range(repeat):
        _strongly_entangling_layer(weights=weights[l], wires=wires, r=ranges[l], imprimitive=imprimitive)


def RandomLayers(weights, wires, repeat=1, ratio_imprim=0.3, imprimitive=CNOT, n_rots=None, rotations=None, seed=42):
    r"""Layers of randomly chosen single qubit rotations and 2-qubit entangling gates, acting
    on randomly chosen qubits.

    The two-qubit gates of type ``imprimitive`` and the rotations are distributed randomly in the circuit.

    If applied to one qubit only, this template will use no imprimitive gates.

    This is an example of two 4-qubit random layers with four Pauli-Y/Pauli-Z rotations :math:`R_y, R_z`,
    controlled-Z gates as imprimitives, as well as ``ratio_imprim=0.3``:
    .. figure:: ../../_static/layer_rnd.png
        :align: center
        :width: 60%
        :target: javascript:void(0);
    .. note::
        Using the default seed (or any other fixed integer seed) generates one and the same circuit in every
        quantum node. To generate different circuit architectures, either use a different random seed, or use ``seed=None``
        together with the ``cache=False`` option when creating a quantum node.
    .. warning::
        When using a random number generator anywhere inside the quantum function without the ``cache=False`` option,
        a new random circuit architecture will be created every time the quantum node is evaluated.

    Args:
        weights (array[float]): array of weights of shape ``(L, k)``,
        wires (Sequence[int]): sequence of qubit indices that the template acts on

    Keyword Args:
        repeat (int): number of layers applied
        ratio_imprim (float): value between 0 and 1 that determines the ratio of imprimitive to rotation gates
        imprimitive (pennylane.ops.Operation): two-qubit gate to use, defaults to :class:`~pennylane.ops.CNOT`
        n_rots (int): number of rotations per layer
        rotations (list[pennylane.ops.Operation]): List of Pauli-X, Pauli-Y and/or Pauli-Z gates. The frequency
            determines how often a particular rotation type is used. Defaults to the use of all three
            rotations with equal frequency.
        seed (int): seed to generate random architecture

    Raises:
        ValueError if arguments do not have the correct format.
    """
    if seed is not None:
        np.random.seed(seed)

    if rotations is None:
        rotations = [RX, RY, RZ]

    #############
    # Input checks
    hyperparams = [repeat, ratio_imprim, imprimitive, n_rots, rotations, seed]
    hyperparam_names = ['repeat', 'ratio_imprim', 'imprimitive', 'n_rots', 'rotations', 'seed']
    _check_no_variable(hyperparams, hyperparam_names)
    wires, n_wires = _check_wires(wires)
    if n_rots is None:
        n_rots = len(wires)
    _check_shape(weights, (repeat, n_rots))
    _check_type(repeat, [int])
    _check_type(ratio_imprim, [float, type(None)])
    _check_type(n_rots, [int, type(None)])
    _check_type(rotations, [list, type(None)])
    _check_type(seed, [int, type(None)])
    ###############

    for l in range(repeat):
        _random_layer(weights=weights[l], wires=wires, ratio_imprim=ratio_imprim, imprimitive=imprimitive,
                      n_rots=n_rots, rotations=rotations, seed=seed)


def CVNeuralNetLayers(theta_1, phi_1, varphi_1, r, phi_r, theta_2, phi_2, varphi_2, a, phi_a, k, wires, repeat=1):
    r"""A sequence of layers of a continuous-variable quantum neural network,
    as specified in `arXiv:1806.06871 <https://arxiv.org/abs/1806.06871>`_.

    The layer consists
    of interferometers, displacement and squeezing gates mimicking the linear transformation of
    a neural network in the x-basis of the quantum system, and uses a Kerr gate
    to introduce a 'quantum' nonlinearity.

    The layers act on the :math:`M` modes given in ``wires``,
    and include interferometers of :math:`K=M(M-1)/2` beamsplitters.

    This example shows a 4-mode CVNeuralNet layer with squeezing gates :math:`S`, displacement gates :math:`D` and
    Kerr gates :math:`K`. The two big blocks are interferometers of type
    :mod:`pennylane.templates.layers.Interferometer`:

    .. figure:: ../../_static/layer_cvqnn.png
        :align: center
        :width: 60%
        :target: javascript:void(0);

    .. note::
       The CV neural network architecture includes :class:`~pennylane.ops.Kerr` operations.
       Make sure to use a suitable device, such as the :code:`strawberryfields.fock`
       device of the `PennyLane-SF <https://github.com/XanaduAI/pennylane-sf>`_ plugin.

    Args:
        theta_1 (array[float]): length :math:`(L, K)` array of transmittivity angles for first interferometer
        phi_1 (array[float]): length :math:`(L, K)` array of phase angles for first interferometer
        varphi_1 (array[float]): length :math:`(L, M)` array of rotation angles to apply after first interferometer
        r (array[float]): length :math:`(L, M)` array of squeezing amounts for :class:`~pennylane.ops.Squeezing` operations
        phi_r (array[float]): length :math:`(L, M)` array of squeezing angles for :class:`~pennylane.ops.Squeezing` operations
        theta_2 (array[float]): length :math:`(L, K)` array of transmittivity angles for second interferometer
        phi_2 (array[float]): length :math:`(L, K)` array of phase angles for second interferometer
        varphi_2 (array[float]): length :math:`(L, M)` array of rotation angles to apply after second interferometer
        a (array[float]): length :math:`(L, M)` array of displacement magnitudes for :class:`~pennylane.ops.Displacement` operations
        phi_a (array[float]): length :math:`(L, M)` array of displacement angles for :class:`~pennylane.ops.Displacement` operations
        k (array[float]): length :math:`(L, M)` array of kerr parameters for :class:`~pennylane.ops.Kerr` operations
        wires (Sequence[int]): sequence of mode indices that the template acts on

    Keyword Args:
        repeat (int): number of layers applied

    Raises:
        ValueError if arguments do not have the correct format.
    """

    #############
    # Input checks
    _check_no_variable([repeat], ['repeat'])
    wires, n_wires = _check_wires(wires)
    n_if = n_wires*(n_wires-1)//2
    weights = [theta_1, phi_1, varphi_1, r, phi_r, theta_2, phi_2, varphi_2, a, phi_a, k]
    shps = [(repeat, n_if), (repeat, n_if), (repeat, n_wires), (repeat, n_wires), (repeat, n_wires),
           (repeat, n_if), (repeat, n_if), (repeat, n_wires), (repeat, n_wires), (repeat, n_wires),
           (repeat, n_wires)]
    _check_shape(weights, shps)
    _check_type(repeat, [int])
    ###############

    for l in range(repeat):
        _cv_neural_net_layer(theta_1=theta_1[l], phi_1=phi_1[l], varphi_1=varphi_1[l],
                             r=r[l], phi_r=phi_r[l],
                             theta_2=theta_2[l], phi_2=phi_2[l], varphi_2=varphi_2[l],
                             a=a[l], phi_a=phi_a[l], k=k[l], wires=wires)


layers = {"StronglyEntanglingLayers", "RandomLayers", "CVNeuralNetLayers"}

__all__ = list(layers)
