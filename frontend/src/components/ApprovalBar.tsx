import type { ApprovalRequest, BoxId } from "../lib/types";

interface Props {
  boxId: BoxId;
  boxName: string;
  request: ApprovalRequest;
  pending: boolean;
  onDecide: (d: "approve" | "block") => void;
}

export function ApprovalBar({ boxId, boxName, request, pending, onDecide }: Props) {
  let path = request.page_url;
  try {
    path = new URL(request.page_url).pathname;
  } catch {
    /* keep raw */
  }
  return (
    <div className="approval" role="alertdialog" aria-labelledby={`approval-${boxId}`}>
      <div className="approval-text">
        <strong id={`approval-${boxId}`}>Approval needed: {boxName}</strong>
        <span>
          {request.reason || "Irreversible action"}. Wants to <code>{request.action}</code>{" "}
          {request.selector && <code>{request.selector}</code>} {path && <>on <code>{path}</code></>}
        </span>
      </div>
      <div className="approval-actions">
        <button className="btn btn-approve" disabled={pending} onClick={() => onDecide("approve")}>
          Approve
        </button>
        <button className="btn btn-block" disabled={pending} onClick={() => onDecide("block")}>
          Block
        </button>
      </div>
    </div>
  );
}
