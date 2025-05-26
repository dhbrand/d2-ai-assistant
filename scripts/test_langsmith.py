from langsmith import Client

client = Client()  # Uses env vars

# Validate API key using info()
try:
    info = client.info()
    print("API key is valid. Info:", info)
except Exception as e:
    print("API key validation failed:", e)

# Log a simple run
try:
    run = client.create_run(
        name="test-run",
        run_type="llm",
        inputs={"prompt": "What is the capital of France?"},
        outputs={"response": "Paris"},
        tags=["test", "demo"]
    )
    print("Logged run:", run)
    print("Type of run:", type(run))
except Exception as e:
    print("Run logging failed:", e)

# List all runs
try:
    runs = list(client.list_runs())
    print(f"Total runs found: {len(runs)}")
    for r in runs[:3]:  # Print up to 3 runs for brevity
        print(r)
except Exception as e:
    print("Failed to list runs:", e) 