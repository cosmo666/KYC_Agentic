import { ChatShell } from "@/components/chat/ChatShell";
import { FaqDrawer } from "@/components/faq/FaqDrawer";

export default function App() {
  return (
    <div className="h-full">
      <ChatShell />
      <FaqDrawer />
    </div>
  );
}
