import "./globals.css"
import Sidebar from "@/components/Sidebar"
import type { ReactNode } from "react"
import { cn } from "@/lib/utils"
import { JetBrains_Mono } from "next/font/google"

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-jetbrains-mono",
})

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={cn("dark", jetbrainsMono.variable)}>
      <body className={cn("min-h-screen bg-background font-sans antialiased")}>
        <div className="flex min-h-screen">
          <Sidebar />
          <main className="flex-1 px-8 py-8 md:pl-72 transition-all duration-300 ease-in-out">
            <div className="mx-auto max-w-7xl animate-in fade-in slide-in-from-bottom-4 duration-500">
              {children}
            </div>
          </main>
        </div>
      </body>
    </html>
  )
}
