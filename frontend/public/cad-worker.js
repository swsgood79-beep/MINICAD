/* DXF bytes stay in this worker. Runtime assets are served from this site's directory. */
let initialized;
async function initialize() {
  if (!initialized)
    initialized = (async () => {
      const base = new URL("./", self.location.href);
      importScripts(new URL("pyodide/pyodide.js", base).href);
      const py = await loadPyodide({
        indexURL: new URL("pyodide/", base).href,
      });
      await py.loadPackage([
        "numpy",
        "fonttools",
        "pyparsing",
        "typing-extensions",
      ]);
      const wheel = await fetch(
        new URL("pyodide/ezdxf-1.4.4-py3-none-any.whl", base),
      );
      if (!wheel.ok) throw new Error("DXF 라이브러리를 불러오지 못했습니다.");
      py.unpackArchive(await wheel.arrayBuffer(), "zip", {
        extractDir: py.runPython("import site; site.getsitepackages()[0]"),
      });
      for (const file of [
        "cad_core.py",
        "browser_runtime.py",
        "dwg_database.py",
      ]) {
        const sourceURL = new URL(file, base);
        sourceURL.search = self.location.search;
        const r = await fetch(sourceURL);
        if (!r.ok) throw new Error("도면 엔진을 불러오지 못했습니다.");
        py.FS.writeFile("/home/pyodide/" + file, await r.text());
      }
      py.runPython("import browser_runtime");
      return py;
    })().catch((error) => {
      initialized = undefined;
      throw error;
    });
  return initialized;
}
let queue = Promise.resolve();
self.onmessage = ({ data: job }) => {
  queue = queue.then(async () => {
    try {
      const py = await initialize();
      if (job.file)
        py.FS.writeFile("/tmp/minicad-input.dxf", new Uint8Array(job.file));
      const dispatch = py.runPython("browser_runtime.dispatch_json");
      let result;
      try {
        result = JSON.parse(
          dispatch(
            job.path,
            JSON.stringify(job.body ?? {}),
            job.documentId ?? null,
            job.filename ?? "drawing.dxf",
          ),
        );
      } finally {
        dispatch.destroy();
      }
      if (result.status === 200 && result.data.export) {
        const bytes = py.FS.readFile("/tmp/minicad-output.dxf");
        py.FS.unlink("/tmp/minicad-output.dxf");
        self.postMessage({ id: job.id, status: 200, bytes }, [bytes.buffer]);
      } else self.postMessage({ id: job.id, ...result });
    } catch (error) {
      self.postMessage({
        id: job.id,
        status: 503,
        data: {
          detail:
            "브라우저 도면 엔진 초기화에 실패했습니다. 새로고침 후 다시 시도하세요. " +
            String(error),
        },
      });
    }
  });
};
