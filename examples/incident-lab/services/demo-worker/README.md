# Demo worker

The worker runs the same bounded service implementation as the demo API with
`LAB_SERVICE=demo-worker`. It processes synthetic jobs through a local request loop,
provides a health check and metrics, and can exit with code 42 or retain a health
failure across restarts in its own disposable named volume. No production data is used.
