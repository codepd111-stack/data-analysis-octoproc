import { Suspense } from "react";
import ChatRoute from "@/components/chat/ChatRoute";

export default function ChatPage() {
  return (
    <Suspense fallback={null}>
      <ChatRoute />
    </Suspense>
  );
}