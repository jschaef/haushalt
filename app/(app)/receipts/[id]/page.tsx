import { ReceiptEditor } from "@/components/receipt-editor";

export default async function ReceiptPage({ params }: PageProps<"/receipts/[id]">) {
  const { id } = await params;
  return <ReceiptEditor id={Number(id)} />;
}
