import sys
import pytest
from langgraph.graph.state import CompiledStateGraph

from backend.core.orchestrator import get_sakhi_agent_graph
from backend.core import session


EXPECTED_FUNCTIONAL_NODES = {
    "load_memory",
    "check_pending_return",
    "check_pending_approval",
    "check_pending_selection",
    "check_fresh_context_lock",
    "detect_intent",
    "catalog_agent",
    "finalize_catalog_listing",
    "customer_agent",
    "growth_agent",
    "general_handler",
    "assemble_reply",
}


def test_graph_compiles_successfully():
    graph = get_sakhi_agent_graph()
    assert isinstance(graph, CompiledStateGraph)


def test_graph_topology_exact_nodes():
    graph = get_sakhi_agent_graph()
    actual_nodes = set(graph.nodes.keys())

    # CompiledStateGraph includes '__start__' alongside functional nodes
    expected_all = EXPECTED_FUNCTIONAL_NODES | {"__start__"}
    assert actual_nodes == expected_all
    assert len(graph.nodes) == 13


def test_graph_entry_point():
    graph = get_sakhi_agent_graph()
    # In LangGraph, __start__ connects to the entry point 'load_memory'
    edges = [e for e in graph.builder.edges if e[0] == "__start__"]
    assert len(edges) == 1
    assert edges[0][1] == "load_memory"


def test_graph_conditional_branches():
    graph = get_sakhi_agent_graph()
    branches = graph.builder.branches

    # Verify all 5 conditional routers are registered on expected source nodes
    registered_branch_nodes = set(branches.keys())
    expected_branch_nodes = {
        "check_pending_return",
        "check_pending_approval",
        "check_pending_selection",
        "check_fresh_context_lock",
        "detect_intent",
    }
    assert registered_branch_nodes == expected_branch_nodes

    # Check destinations of each branch
    return_branch = branches["check_pending_return"]["route_pending_return"]
    assert set(return_branch.ends.values()) == {"assemble_reply", "check_pending_approval"}

    approval_branch = branches["check_pending_approval"]["route_pending"]
    assert set(approval_branch.ends.values()) == {"finalize_catalog_listing", "assemble_reply", "check_pending_selection"}

    selection_branch = branches["check_pending_selection"]["route_pending_selection"]
    assert set(selection_branch.ends.values()) == {"catalog_agent", "customer_agent", "check_fresh_context_lock"}

    lock_branch = branches["check_fresh_context_lock"]["route_fresh_context_lock"]
    assert set(lock_branch.ends.values()) == {"assemble_reply", "detect_intent"}

    intent_branch = branches["detect_intent"]["route_decision"]
    assert set(intent_branch.ends.values()) == {"catalog_agent", "customer_agent", "growth_agent", "general_handler"}


def test_graph_exit_edges():
    graph = get_sakhi_agent_graph()
    # All agent nodes & finalize_catalog_listing must route to assemble_reply
    direct_edges = graph.builder.edges
    assert ("catalog_agent", "assemble_reply") in direct_edges
    assert ("finalize_catalog_listing", "assemble_reply") in direct_edges
    assert ("customer_agent", "assemble_reply") in direct_edges
    assert ("growth_agent", "assemble_reply") in direct_edges
    assert ("general_handler", "assemble_reply") in direct_edges
    assert ("assemble_reply", "__end__") in direct_edges


def test_repeated_graph_compilation():
    g1 = get_sakhi_agent_graph()
    g2 = get_sakhi_agent_graph()
    assert len(g1.nodes) == len(g2.nodes) == 13


def test_architecture_layering_no_lower_module_imports_orchestrator():
    """Verify clean dependency hierarchy: lower layers must never import orchestrator."""
    import backend.core.agents.growth as ag_growth
    import backend.core.agents.general as ag_general
    import backend.core.agents.returns as ag_returns
    import backend.core.agents.catalog as ag_catalog
    import backend.core.agents.customer as ag_customer
    import backend.core.rag.formatting as rag_format
    import backend.core.rag.embeddings as rag_embed
    import backend.core.rag.retrieval as rag_retrieval
    import backend.core.routing.approval as route_app
    import backend.core.session as core_session
    import backend.core.state as core_state

    modules_to_inspect = [
        ag_growth, ag_general, ag_returns, ag_catalog, ag_customer,
        rag_format, rag_embed, rag_retrieval, route_app,
        core_session, core_state
    ]

    for mod in modules_to_inspect:
        assert not hasattr(mod, "get_sakhi_agent_graph"), f"{mod.__name__} illegally imports orchestrator"
        assert "orchestrator" not in [name for name, _ in mod.__dict__.items()], f"{mod.__name__} has orchestrator symbol"
