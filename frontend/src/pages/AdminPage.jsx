import { useState } from "react";
import { LoaderCircle, ShieldAlert, Trash2, UserRoundCog, Users } from "lucide-react";

import { ROLE_LABELS } from "../constants";
import { listUsers, updateUserRole, deleteUser } from "../api/client";
import { EmptyState, StatusBadge } from "../components/ui";

export function AdminPage({ workspace }) {
  const [users, setUsers] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [editingUser, setEditingUser] = useState(null);
  const [newRole, setNewRole] = useState("");

  async function refreshUsers() {
    setLoading(true);
    setError("");
    try {
      const data = await listUsers();
      setUsers(data.users || []);
    } catch (e) {
      setError(e?.response?.data?.message || e.message || "加载用户列表失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleUpdateRole(username) {
    if (!newRole) return;
    setError("");
    try {
      await updateUserRole(username, newRole);
      await refreshUsers();
      setEditingUser(null);
      setNewRole("");
    } catch (e) {
      setError(e?.response?.data?.message || e.message || "更新角色失败");
    }
  }

  async function handleDeleteUser(username) {
    if (!window.confirm(`确定删除用户 "${username}"？此操作不可撤销。`)) return;
    setError("");
    try {
      await deleteUser(username);
      await refreshUsers();
    } catch (e) {
      setError(e?.response?.data?.message || e.message || "删除用户失败");
    }
  }

  if (workspace.role !== "admin") {
    return (
      <div className="page-content">
        <EmptyState icon={ShieldAlert} title="需要管理员权限" description="当前角色无法访问系统管理页面。" />
      </div>
    );
  }

  if (!users && !loading) {
    refreshUsers();
  }

  return (
    <div className="page-content admin-page">
      <div className="page-toolbar">
        <div className="toolbar-left">
          <h2 className="toolbar-title"><Users size={20} />用户管理</h2>
          <StatusBadge value={`${users?.length || 0} 个用户`} tone="teal" dot={false} />
        </div>
        <button className="secondary-button" onClick={refreshUsers} disabled={loading}>
          {loading ? <LoaderCircle size={15} className="spin" /> : null}
          刷新
        </button>
      </div>

      {error ? <div className="error-banner"><span>{error}</span><button onClick={() => setError("")}>×</button></div> : null}

      {loading && !users ? (
        <div className="loading-center"><LoaderCircle size={24} className="spin" /></div>
      ) : users?.length ? (
        <div className="table-card">
          <table className="data-table">
            <thead>
              <tr>
                <th>用户名</th>
                <th>角色</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.username}>
                  <td className="mono-cell">{u.username}</td>
                  <td>
                    {editingUser === u.username ? (
                      <select value={newRole} onChange={(e) => setNewRole(e.target.value)} className="compact-select">
                        <option value="">选择角色...</option>
                        {Object.entries(ROLE_LABELS).map(([value, label]) => (
                          <option key={value} value={value}>{label}</option>
                        ))}
                      </select>
                    ) : (
                      <StatusBadge value={ROLE_LABELS[u.role] || u.role} tone={u.role === "admin" ? "warm" : "teal"} dot={false} />
                    )}
                  </td>
                  <td className="mono-cell">{u.created_at?.slice(0, 10) || "-"}</td>
                  <td className="action-cell">
                    {editingUser === u.username ? (
                      <>
                        <button className="mini-button primary" onClick={() => handleUpdateRole(u.username)}>保存</button>
                        <button className="mini-button" onClick={() => { setEditingUser(null); setNewRole(""); }}>取消</button>
                      </>
                    ) : (
                      <>
                        <button
                          className="mini-button"
                          onClick={() => { setEditingUser(u.username); setNewRole(u.role); }}
                          disabled={u.username === workspace.auth.user?.username}
                          title={u.username === workspace.auth.user?.username ? "不能修改自己的角色" : "修改角色"}
                        >
                          <UserRoundCog size={14} />
                        </button>
                        <button
                          className="mini-button danger"
                          onClick={() => handleDeleteUser(u.username)}
                          disabled={u.username === workspace.auth.user?.username}
                          title={u.username === workspace.auth.user?.username ? "不能删除自己" : "删除用户"}
                        >
                          <Trash2 size={14} />
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState title="暂无用户数据" description="系统尚未注册任何用户。" />
      )}
    </div>
  );
}
