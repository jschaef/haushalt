import { Suspense } from "react";
import { ReceiptList } from "@/components/receipt-list";

export default function ReceiptsPage() {
  return (
    <Suspense>
      <ReceiptList />
    </Suspense>
  );
}
