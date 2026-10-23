import { useEffect, useState } from "react";
import { api } from "../api.js";

const EXAMPLES = {
  C001: { tx: "T1002", text: "I was charged twice at Viva Fresh for the same shopping. I only paid once at the till." },
  C002: { tx: "T2001", text: "I did not make this purchase at ElectroWorld Lagos. My card is with me and I was asleep." },
  C003: { tx: "T3001", text: "I cancelled my StreamPlus subscription last month but I was charged again." },
};

export default function NewDisputeForm({ onCreated }) {
  const [customers, setCustomers] = useState([]);
  const [customerId, setCustomerId] = useState("");
  const [transactionId, setTransactionId] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.customers().then(setCustomers).catch((e) => setError(e.message));
  }, []);

  const customer = customers.find((c) => c.id === customerId);

  const chooseCustomer = (id) => {
    setCustomerId(id);
    setTransactionId(EXAMPLES[id]?.tx || "");
    setDescription(EXAMPLES[id]?.text || "");
  };

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const dispute = await api.create({ customer_id: customerId, transaction_id: transactionId, description });
      onCreated(dispute);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form className="card" onSubmit={submit}>
      <h2>New dispute</h2>
      <label>
        Customer
        <select value={customerId} onChange={(e) => chooseCustomer(e.target.value)} required>
          <option value="">Select customer…</option>
          {customers.map((c) => (
            <option key={c.id} value={c.id}>{c.id} · {c.name}</option>
          ))}
        </select>
      </label>
      <label>
        Transaction
        <select value={transactionId} onChange={(e) => setTransactionId(e.target.value)} required disabled={!customer}>
          <option value="">Select transaction…</option>
          {customer?.transactions.map((t) => (
            <option key={t.id} value={t.id}>
              {new Date(t.created_at).toLocaleDateString()} · {t.merchant} · {t.amount.toFixed(2)} {t.currency}
            </option>
          ))}
        </select>
      </label>
      <label>
        What happened?
        <textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} minLength={10} required />
      </label>
      {error && <div className="error">{error}</div>}
      <button className="primary" disabled={loading}>
        {loading ? "Agents are working…" : "Submit dispute"}
      </button>
    </form>
  );
}