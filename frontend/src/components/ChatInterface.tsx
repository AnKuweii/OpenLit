import { useState, useRef, useEffect, useMemo } from "react";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";
import { ScrollArea } from "./ui/scroll-area";
import { Avatar, AvatarFallback } from "./ui/avatar";
import { Send, User, Bot, Sparkles } from "lucide-react";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { processChatStream, clearSession } from "../services/api";
import { toast } from "sonner";

type Reference = {
  id: number;
  text: string;
  page: number;
  citationId?: string;
  rank?: number;
  snippet?: string;
};

type Message = {
  id: string;
  type: "user" | "assistant";
  content: string;
  timestamp: Date;
  references?: Reference[];
};

type ChatInterfaceProps = {
  onClearChat: () => void;
  fileId?: string;
  fileName?: string;
  threadId?: string;
};

export function ChatInterface({
  onClearChat,
  fileId,
  fileName,
  threadId = "default",
}: ChatInterfaceProps) {
  const initialAssistant =
    "Hello! I'm your AI assistant. You can chat directly, and if you upload a PDF I can answer with document-grounded citations.";

  const [messages, setMessages] = useState<Message[]>([
    { id: "welcome", type: "assistant", content: initialAssistant, timestamp: new Date() },
  ]);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);

  const [currentResponse, setCurrentResponse] = useState("");
  const [currentReferences, setCurrentReferences] = useState<Reference[]>([]);

  const currentResponseRef = useRef("");
  const currentReferencesRef = useRef<Reference[]>([]);
  const citationIdsRef = useRef<Set<string>>(new Set());

  const abortRef = useRef<AbortController | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const canSend = useMemo(() => input.trim().length > 0 && !isTyping, [input, isTyping]);

  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping, currentResponse, currentReferences]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + "px";
    }
  }, [input]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const handleSend = async () => {
    if (!canSend) return;

    abortRef.current?.abort();

    const userMessage: Message = {
      id: Date.now().toString(),
      type: "user",
      content: input,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMessage]);

    const userText = input;
    setInput("");
    setIsTyping(true);
    setCurrentResponse("");
    setCurrentReferences([]);
    currentResponseRef.current = "";
    currentReferencesRef.current = [];
    citationIdsRef.current = new Set();

    try {
      await processChatStream(
        userText,
        (token: string) => {
          setCurrentResponse((prev) => prev + token);
          currentResponseRef.current += token;
        },
        (c: {
          citation_id: string;
          fileId: string;
          rank: number;
          page: number;
          previewUrl: string;
          snippet?: string;
        }) => {
          if (!c.citation_id || citationIdsRef.current.has(c.citation_id)) return;
          citationIdsRef.current.add(c.citation_id);

          const newRef: Reference = {
            id: currentReferencesRef.current.length + 1,
            text: `第 ${c.page ?? "?"} 页相关内容`,
            page: c.page ?? 0,
            citationId: c.citation_id,
            rank: c.rank,
            snippet: c.snippet,
          };

          setCurrentReferences((prev) => [...prev, newRef]);
          currentReferencesRef.current = [...currentReferencesRef.current, newRef];
        },
        (meta: { used_retrieval: boolean }) => {
          const finalResponse = currentResponseRef.current;
          const finalRefs = [...currentReferencesRef.current];

          const assistantMessage: Message = {
            id: (Date.now() + 1).toString(),
            type: "assistant",
            content: finalResponse || "_（空响应）_",
            timestamp: new Date(),
            references: finalRefs.length ? finalRefs : undefined,
          };

          setMessages((prev) => [...prev, assistantMessage]);
          setIsTyping(false);
          setCurrentResponse("");
          setCurrentReferences([]);
          currentResponseRef.current = "";
          currentReferencesRef.current = [];
          citationIdsRef.current.clear();

          if (meta?.used_retrieval) {
            toast.success("Response grounded by document context");
          }
          textareaRef.current?.focus();
        },
        (errText: string) => {
          console.error("Chat error:", errText);
          setIsTyping(false);
          setCurrentResponse("");
          setCurrentReferences([]);
          currentResponseRef.current = "";
          currentReferencesRef.current = [];
          citationIdsRef.current.clear();

          const errorMessage: Message = {
            id: (Date.now() + 1).toString(),
            type: "assistant",
            content: `抱歉，处理你的请求时出现错误：${errText}`,
            timestamp: new Date(),
          };
          setMessages((prev) => [...prev, errorMessage]);
          toast.error("Failed to get response");
        },
        fileId,
        threadId,
      );
    } catch (e) {
      console.error("Chat request failed:", e);
      setIsTyping(false);
      setCurrentResponse("");
      setCurrentReferences([]);
      currentResponseRef.current = "";
      currentReferencesRef.current = [];
      citationIdsRef.current.clear();
      toast.error("Failed to send message");
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const clearChat = async () => {
    try {
      abortRef.current?.abort();
      await clearSession(threadId);
      setMessages([
        {
          id: "welcome",
          type: "assistant",
          content: initialAssistant,
          timestamp: new Date(),
        },
      ]);
      onClearChat();
      toast.success("Chat history cleared");
    } catch (error) {
      if (error instanceof TypeError && String(error).includes("Failed to fetch")) {
        setMessages([
          {
            id: "welcome",
            type: "assistant",
            content: initialAssistant,
            timestamp: new Date(),
          },
        ]);
        onClearChat();
        toast.success("Chat history cleared (Local)");
        return;
      }
      console.error("Failed to clear chat:", error);
      toast.error("Failed to clear chat history");
    } finally {
      textareaRef.current?.focus();
    }
  };

  return (
    <div className="glass-panel-bright h-full flex flex-col max-h-full relative overflow-hidden">
      <div className="absolute inset-0 opacity-[0.03]">
        <div className="absolute inset-0 bg-gradient-to-br from-amber-500/30 via-transparent to-rose-500/20"></div>
      </div>

      <div className="relative px-5 py-4 border-b border-border/50 flex-shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/25">
              <Sparkles className="w-4 h-4 text-amber-400" />
            </div>
            <div>
              <h2 className="elegant-title text-base">AI Assistant</h2>
              {fileId && fileName && (
                <p className="text-xs text-muted-foreground/70 mt-0.5">
                  Analyzing: {fileName}
                </p>
              )}
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={clearChat}
            className="text-muted-foreground hover:text-white hover:bg-destructive/80 hover:border-destructive/60 border border-border/50 transition-all duration-200 rounded-xl text-xs cursor-pointer"
          >
            Clear
          </Button>
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-hidden relative">
        <ScrollArea className="h-full">
          <div className="p-5">
            <div className="space-y-3">
              {messages.map((m) => (
                <div key={m.id} className={`flex gap-3 ${m.type === "user" ? "justify-end" : "justify-start"}`}>
                  {m.type === "assistant" && (
                    <Avatar className="w-8 h-8 border border-amber-500/25 flex-shrink-0">
                      <AvatarFallback className="bg-gradient-to-br from-amber-500/10 to-rose-500/10">
                        <Bot className="w-4 h-4 text-amber-400" />
                      </AvatarFallback>
                    </Avatar>
                  )}

                  <div className={`max-w-[80%] ${m.type === "user" ? "order-first" : ""}`}>
                    <div
                      className={`p-3.5 rounded-2xl ${
                        m.type === "user"
                          ? "bg-gradient-to-br from-amber-500 to-amber-600 text-primary-foreground ml-auto border border-amber-500/40"
                          : "bg-secondary/30 border border-border/30 backdrop-blur-sm"
                      }`}
                      style={{ boxShadow: m.type === "user" ? '0 4px 16px rgba(245, 158, 11, 0.2)' : '0 2px 12px rgba(0,0,0,0.1)' }}
                    >
                      {m.type === "user" ? (
                        <p className="text-primary-foreground leading-relaxed text-sm whitespace-pre-wrap">{m.content}</p>
                      ) : (
                        <MarkdownRenderer content={m.content} references={m.references} />
                      )}
                    </div>
                  </div>

                  {m.type === "user" && (
                    <Avatar className="w-8 h-8 border border-border/30 flex-shrink-0">
                      <AvatarFallback className="bg-gradient-to-br from-stone-700/60 to-stone-800/60">
                        <User className="w-4 h-4 text-stone-300" />
                      </AvatarFallback>
                    </Avatar>
                  )}
                </div>
              ))}

              {isTyping && (
                <div className="flex gap-3">
                  <Avatar className="w-8 h-8 border border-amber-500/25 flex-shrink-0">
                    <AvatarFallback className="bg-gradient-to-br from-amber-500/10 to-rose-500/10">
                      <Bot className="w-4 h-4 text-amber-400" />
                    </AvatarFallback>
                  </Avatar>
                  <div className="max-w-[80%]">
                    <div className="bg-secondary/30 border border-border/30 backdrop-blur-sm rounded-2xl p-3.5" style={{ boxShadow: '0 2px 12px rgba(0,0,0,0.1)' }}>
                      {currentResponse ? (
                        <MarkdownRenderer content={currentResponse} references={currentReferences} />
                      ) : (
                        <div className="flex space-x-2 py-1">
                          <div className="w-1.5 h-1.5 bg-amber-400/60 rounded-full animate-bounce"></div>
                          <div className="w-1.5 h-1.5 bg-amber-400/60 rounded-full animate-bounce" style={{ animationDelay: "0.15s" }}></div>
                          <div className="w-1.5 h-1.5 bg-amber-400/60 rounded-full animate-bounce" style={{ animationDelay: "0.3s" }}></div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          </div>
        </ScrollArea>
      </div>

      <div className="relative px-5 py-4 border-t border-border/40 flex-shrink-0 bg-card/30">
        <div className="flex gap-3 items-end">
          <div className="relative flex-1">
            <Textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder={fileId ? "Ask a question about your document..." : "Ask anything… (upload a PDF to enable RAG)"}
              className="flex-1 bg-input/50 border-border/30 focus:border-amber-500/40 glow-ring text-foreground placeholder:text-muted-foreground/60 rounded-xl px-4 py-3 backdrop-blur-sm resize-none min-h-[48px] max-h-[120px] text-sm leading-relaxed flex items-center"
              disabled={isTyping}
              rows={1}
            />
          </div>
          <Button
            onClick={handleSend}
            disabled={!canSend}
            className="bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-600 hover:to-amber-700 text-primary-foreground h-[48px] w-[48px] p-0 rounded-xl transition-all duration-200 border border-amber-500/40 flex-shrink-0"
            style={{ boxShadow: '0 4px 16px rgba(245, 158, 11, 0.2)' }}
          >
            <Send className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
