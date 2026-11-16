import type { HistoryMessage } from "@/api";
import type { Message } from "@/components/askrepo/conversation";

export function requestHistory(messages: Message[]): HistoryMessage[] {
  const recent = messages
    .filter(
      (message) => message.response && !message.streaming && !message.stopped && !message.error,
    )
    .flatMap((message): HistoryMessage[] => [
      { role: "user", content: message.question.slice(0, 500) },
      {
        role: "assistant",
        content:
          message.response!.answer.length > 1200
            ? message.response!.answer.slice(0, 895) +
              "\n...\n" +
              message.response!.answer.slice(-300)
            : message.response!.answer,
      },
    ])
    .slice(-6);
  return recent;
}
