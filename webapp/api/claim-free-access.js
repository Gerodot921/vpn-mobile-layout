const { forwardJson } = require("./_lib");

module.exports = async (req, res) => {
  if (req.method !== "POST") {
    res.status(405).json({ ok: false, error: "Method not allowed" });
    return;
  }

  try {
    const result = await forwardJson("/api/claim-free-access", req.body || {});
    res.status(result.status).json(result.body);
  } catch (error) {
    res.status(500).json({ ok: false, error: error.message || "Failed to claim access" });
  }
};