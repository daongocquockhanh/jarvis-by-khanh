import sys
from ingest import ingest_documents
from agent import ask


def cmd_ingest():
    print("Ingesting documents...")
    ingest_documents()


def cmd_ask(question: str):
    print(f"Question: {question}\n")
    answer = ask(question)
    print(f"Answer:\n{answer}")


def cmd_chat():
    print("Interactive chat (type 'quit' to exit)\n")
    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        answer = ask(question)
        print(f"\nAssistant: {answer}\n")


def cmd_voice():
    from jarvis import run_assistant

    run_assistant()


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python main.py ingest          - Load documents into vector store")
        print('  python main.py ask "question"   - Ask a single question')
        print("  python main.py chat             - Interactive chat mode")
        print("  python main.py voice            - JARVIS voice assistant mode")
        sys.exit(1)

    command = sys.argv[1]

    if command == "ingest":
        cmd_ingest()
    elif command == "ask":
        if len(sys.argv) < 3:
            print('Usage: python main.py ask "your question here"')
            sys.exit(1)
        cmd_ask(sys.argv[2])
    elif command == "chat":
        cmd_chat()
    elif command == "voice":
        cmd_voice()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
