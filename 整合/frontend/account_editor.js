const $ = (selector) => document.querySelector(selector);

function sessionHeaders() {
  let session = {};
  try {
    session = JSON.parse(localStorage.getItem("monitorSession") || "{}");
  } catch {
    session = {};
  }
  return {
    "Content-Type": "application/json",
    "X-User-Role": session.role || "user",
    "X-User-Name": session.username || "",
  };
}

async function fetchJson(url, options = {}) {
  const res = await fetch(url, { ...options, headers: { ...sessionHeaders(), ...(options.headers || {}) } });
  const data = await res.json();
  if (!res.ok || data.ok === false) throw new Error(data.error || "请求失败");
  return data;
}

$("#accountCreateForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = $("#accountMessage");
  message.textContent = "";
  try {
    await fetchJson("/api/admin/accounts", {
      method: "POST",
      body: JSON.stringify({
        username: $("#accountUsername").value,
        display_name: $("#accountDisplayName").value,
        password: $("#accountPassword").value,
        phone: $("#accountPhone").value,
        department: $("#accountDepartment").value,
        role: $("#accountRole").value,
        enabled: $("#accountEnabled").value === "true",
      }),
    });
    $("#accountCreateForm").reset();
    message.textContent = "账号已创建。";
    message.className = "form-message ok";
  } catch (error) {
    message.textContent = error.message;
    message.className = "form-message error";
  }
});
