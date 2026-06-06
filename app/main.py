print("Main is loaded")
from app.workflows.research_graph import build_graph


def main():

    graph = build_graph()

    initial_state = {
        "query": "Research MCP adoption in enterprises",
        "tasks": [],
        "findings": [],
        "verified_findings": [],
        "report": "",
        "metadata": {}
    }

    result = graph.invoke(initial_state)

    print("\n")
    print("=" * 50)
    print("FINAL REPORT")
    print("=" * 50)
    print("\n")

    print(result["report"])


if __name__ == "__main__":
    main()