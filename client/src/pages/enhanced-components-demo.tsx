import { useState } from "react";
import {
  EnhancedModernButton,
  EnhancedModernCard,
  EnhancedModernInput,
  EnhancedAvatar,
  EnhancedBadge
} from "@/components/ui";

export default function EnhancedComponentsDemo() {
  const [buttonState, setButtonState] = useState<string>("default");
  const [inputValue, setInputValue] = useState<string>("");
  const [inputState, setInputState] = useState<"default" | "focus" | "error" | "success">("default");
  const [avatarState, setAvatarState] = useState<"default" | "loading" | "error" | "success" | "offline" | "online">("default");
  const [badgeState, setBadgeState] = useState<"default" | "loading" | "error" | "success">("default");

  return (
    <div className="min-h-screen terminal-bg p-8 space-y-8">
      <h1 className="text-3xl font-mono text-cyber-blue mb-6">Enhanced Components Demo</h1>
      <p className="text-gray-300 mb-4">Showcasing glassmorphism variants, state variants, and enhanced interactions</p>

      {/* Enhanced Modern Button Demo */}
      <section className="space-y-6">
        <h2 className="text-xl font-mono text-cyber-green">Enhanced Modern Button</h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          <EnhancedModernButton
            variant="default"
            size="default"
            onClick={() => setButtonState("default")}
            className={`${buttonState === "default" ? "ring-2 ring-cyber-blue" : ""}`}
          >
            Default
          </EnhancedModernButton>
          <EnhancedModernButton
            variant="glass"
            size="default"
            onClick={() => setButtonState("glass")}
            className={`${buttonState === "glass" ? "ring-2 ring-cyber-blue" : ""}`}
          >
            Glass
          </EnhancedModernButton>
          <EnhancedModernButton
            variant="glass-dark"
            size="default"
            onClick={() => setButtonState("glass-dark")}
            className={`${buttonState === "glass-dark" ? "ring-2 ring-cyber-blue" : ""}`}
          >
            Glass Dark
          </EnhancedModernButton>
          <EnhancedModernButton
            variant="neon-glass"
            size="default"
            onClick={() => setButtonState("neon-glass")}
            className={`${buttonState === "neon-glass" ? "ring-2 ring-cyber-blue" : ""}`}
          >
            Neon Glass
          </EnhancedModernButton>
          <EnhancedModernButton
            variant="outline"
            size="default"
            onClick={() => setButtonState("outline")}
            className={`${buttonState === "outline" ? "ring-2 ring-cyber-blue" : ""}`}
          >
            Outline
          </EnhancedModernButton>
          <EnhancedModernButton
            variant="subtle"
            size="default"
            onClick={() => setButtonState("subtle")}
            className={`${buttonState === "subtle" ? "ring-2 ring-cyber-blue" : ""}`}
          >
            Subtle
          </EnhancedModernButton>
          <EnhancedModernButton
            variant="outline"
            size="default"
            onClick={() => setButtonState("elevated")}
            className={`${buttonState === "elevated" ? "ring-2 ring-cyber-blue" : ""}`}
          >
            Elevated Style
          </EnhancedModernButton>
          <EnhancedModernButton
            variant="secondary"
            size="default"
            onClick={() => setButtonState("floating")}
            className={`${buttonState === "floating" ? "ring-2 ring-cyber-blue" : ""}`}
          >
            Secondary
          </EnhancedModernButton>
        </div>

        {/* Button States */}
        <div className="space-x-4">
          <EnhancedModernButton
            variant="glass"
            size="lg"
            isLoading={buttonState === "loading"}
            loadingText="Processing..."
            onClick={() => {
              setButtonState("loading");
              setTimeout(() => setButtonState("glass"), 2000);
            }}
          >
            Loading State
          </EnhancedModernButton>
          <EnhancedModernButton
            variant="neon-glass"
            size="lg"
            isLoading={buttonState === "success"}
            loadingText="Complete!"
            onClick={() => {
              setButtonState("success");
              setTimeout(() => setButtonState("neon-glass"), 1500);
            }}
          >
            Success State
          </EnhancedModernButton>
        </div>
      </section>

      {/* Enhanced Modern Card Demo */}
      <section className="space-y-6">
        <h2 className="text-xl font-mono text-cyber-green">Enhanced Modern Card</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          <EnhancedModernCard
            variant="default"
            state="default"
            size="default"
            className="h-64"
          >
            <h3 className="font-mono text-cyber-blue mb-2">Default Card</h3>
            <p className="text-gray-300">Standard card with hover effects</p>
          </EnhancedModernCard>

          <EnhancedModernCard
            variant="glass"
            state="default"
            size="default"
            className="h-64"
          >
            <h3 className="font-mono text-cyber-blue mb-2">Glass Card</h3>
            <p className="text-gray-300">Card with glassmorphism effect</p>
          </EnhancedModernCard>

          <EnhancedModernCard
            variant="glass-dark"
            state="default"
            size="default"
            className="h-64"
          >
            <h3 className="font-mono text-cyber-blue mb-2">Dark Glass Card</h3>
            <p className="text-gray-300">Card with dark glassmorphism effect</p>
          </EnhancedModernCard>

          <EnhancedModernCard
            variant="neon-glass"
            state="default"
            size="default"
            className="h-64"
          >
            <h3 className="font-mono text-cyber-blue mb-2">Neon Glass Card</h3>
            <p className="text-gray-300">Card with neon glassmorphism effect</p>
          </EnhancedModernCard>

          <EnhancedModernCard
            variant="default"
            state="loading"
            size="default"
            className="h-64"
          >
            <h3 className="font-mono text-cyber-blue mb-2">Loading State</h3>
          </EnhancedModernCard>

          <EnhancedModernCard
            variant="default"
            state="error"
            size="default"
            className="h-64"
          >
            <h3 className="font-mono text-cyber-blue mb-2">Error State</h3>
          </EnhancedModernCard>

          <EnhancedModernCard
            variant="default"
            state="success"
            size="default"
            className="h-64"
          >
            <h3 className="font-mono text-cyber-blue mb-2">Success State</h3>
          </EnhancedModernCard>

          <EnhancedModernCard
            variant="default"
            state="empty"
            size="default"
            className="h-64"
          >
            <h3 className="font-mono text-cyber-blue mb-2">Empty State</h3>
          </EnhancedModernCard>
        </div>

        {/* Card Sizes */}
        <div className="flex space-x-4">
          <EnhancedModernCard
            variant="glass"
            state="default"
            size="sm"
            className="h-48"
          >
            <h3 className="font-mono text-cyber-blue mb-2">Small Card</h3>
          </EnhancedModernCard>
          <EnhancedModernCard
            variant="glass"
            state="default"
            size="default"
            className="h-48"
          >
            <h3 className="font-mono text-cyber-blue mb-2">Default Card</h3>
          </EnhancedModernCard>
          <EnhancedModernCard
            variant="glass"
            state="default"
            size="lg"
            className="h-48"
          >
            <h3 className="font-mono text-cyber-blue mb-2">Large Card</h3>
          </EnhancedModernCard>
        </div>
      </section>

      {/* Enhanced Modern Input Demo */}
      <section className="space-y-6">
        <h2 className="text-xl font-mono text-cyber-green">Enhanced Modern Input</h2>
        <div className="space-y-6">
          <div className="space-y-4">
            <label htmlFor="glass-input" className="font-mono text-cyber-blue">
              Glass Input
            </label>
            <EnhancedModernInput
              variant="glass"
              placeholder="Enter text with glass effect"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onFocus={() => setInputState("focus")}
              onBlur={() => setInputState("default")}
              className="w-full"
            />
          </div>

          <div className="space-y-4">
            <label htmlFor="neon-glass-input" className="font-mono text-cyber-blue">
              Neon Glass Input
            </label>
            <EnhancedModernInput
              variant="neon-glass"
              placeholder="Enter text with neon glass effect"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              className="w-full"
            />
          </div>

          <div className="space-y-4">
            <label htmlFor="input-state" className="font-mono text-cyber-blue">
              Input States
            </label>
            <div className="space-x-4">
              <EnhancedModernInput
                variant="glass"
                placeholder="Normal"
                state="default"
                className="w-32"
              />
              <EnhancedModernInput
                variant="glass"
                placeholder="Focused"
                state="focus"
                className="w-32"
              />
              <EnhancedModernInput
                variant="glass"
                placeholder="Error"
                state="error"
                className="w-32"
              />
              <EnhancedModernInput
                variant="glass"
                placeholder="Success"
                state="success"
                className="w-32"
              />
            </div>
          </div>

          <div className="space-y-4">
            <label htmlFor="input-sizes" className="font-mono text-cyber-blue">
              Input Sizes
            </label>
            <div className="flex space-x-4">
              <EnhancedModernInput
                variant="glass"
                placeholder="Extra Small"
                size="xs"
                className="w-24"
              />
              <EnhancedModernInput
                variant="glass"
                placeholder="Small"
                size="sm"
                className="w-32"
              />
              <EnhancedModernInput
                variant="glass"
                placeholder="Default"
                size="default"
                className="w-40"
              />
              <EnhancedModernInput
                variant="glass"
                placeholder="Large"
                size="lg"
                className="w-48"
              />
              <EnhancedModernInput
                variant="glass"
                placeholder="Extra Large"
                size="xl"
                className="w-56"
              />
            </div>
          </div>
        </div>
      </section>

      {/* Enhanced Avatar Demo */}
      <section className="space-y-6">
        <h2 className="text-xl font-mono text-cyber-green">Enhanced Avatar</h2>
        <div className="space-y-6">
          <div className="space-y-4">
            <label htmlFor="avatar-variants" className="font-mono text-cyber-blue">
              Avatar Variants
            </label>
            <div className="flex space-x-4">
              <EnhancedAvatar
                variant="default"
                size="lg"
                className="h-12 w-12"
              >
                <img src="https://i.pravatar.cc/150?img=1" alt="Avatar 1" />
              </EnhancedAvatar>
              <EnhancedAvatar
                variant="glass"
                size="lg"
                className="h-12 w-12"
              >
                <img src="https://i.pravatar.cc/150?img=2" alt="Avatar 2" />
              </EnhancedAvatar>
              <EnhancedAvatar
                variant="glass-dark"
                size="lg"
                className="h-12 w-12"
              >
                <img src="https://i.pravatar.cc/150?img=3" alt="Avatar 3" />
              </EnhancedAvatar>
              <EnhancedAvatar
                variant="neon-glass"
                size="lg"
                className="h-12 w-12"
              >
                <img src="https://i.pravatar.cc/150?img=4" alt="Avatar 4" />
              </EnhancedAvatar>
              <EnhancedAvatar
                variant="outline"
                size="lg"
                className="h-12 w-12"
              >
                <img src="https://i.pravatar.cc/150?img=5" alt="Avatar 5" />
              </EnhancedAvatar>
            </div>
          </div>

          <div className="space-y-4">
            <label htmlFor="avatar-sizes" className="font-mono text-cyber-blue">
              Avatar Sizes
            </label>
            <div className="flex space-x-4">
              <EnhancedAvatar
                variant="glass"
                size="xs"
                className="h-6 w-6"
              >
                <img src="https://i.pravatar.cc/150?img=6" alt="Avatar XS" />
              </EnhancedAvatar>
              <EnhancedAvatar
                variant="glass"
                size="sm"
                className="h-8 w-8"
              >
                <img src="https://i.pravatar.cc/150?img=7" alt="Avatar SM" />
              </EnhancedAvatar>
              <EnhancedAvatar
                variant="glass"
                size="default"
                className="h-10 w-10"
              >
                <img src="https://i.pravatar.cc/150?img=8" alt="Avatar Default" />
              </EnhancedAvatar>
              <EnhancedAvatar
                variant="glass"
                size="lg"
                className="h-12 w-12"
              >
                <img src="https://i.pravatar.cc/150?img=9" alt="Avatar LG" />
              </EnhancedAvatar>
              <EnhancedAvatar
                variant="glass"
                size="xl"
                className="h-14 w-14"
              >
                <img src="https://i.pravatar.cc/150?img=10" alt="Avatar XL" />
              </EnhancedAvatar>
            </div>
          </div>

          <div className="space-y-4">
            <label htmlFor="avatar-shapes" className="font-mono text-cyber-blue">
              Avatar Shapes
            </label>
            <div className="flex space-x-4">
              <EnhancedAvatar
                variant="glass"
                size="lg"
                shape="round"
                className="h-12 w-12"
              >
                <img src="https://i.pravatar.cc/150?img=11" alt="Avatar Round" />
              </EnhancedAvatar>
              <EnhancedAvatar
                variant="glass"
                size="lg"
                shape="square"
                className="h-12 w-12"
              >
                <img src="https://i.pravatar.cc/150?img=12" alt="Avatar Square" />
              </EnhancedAvatar>
            </div>
          </div>

          <div className="space-y-4">
            <label htmlFor="avatar-states" className="font-mono text-cyber-blue">
              Avatar States
            </label>
            <div className="flex space-x-4">
              <EnhancedAvatar
                variant="glass"
                size="lg"
                state="default"
                className="h-12 w-12"
              >
                <img src="https://i.pravatar.cc/150?img=13" alt="Avatar Default" />
              </EnhancedAvatar>
              <EnhancedAvatar
                variant="glass"
                size="lg"
                state="loading"
                className="h-12 w-12"
              >
                <img src="https://i.pravatar.cc/150?img=14" alt="Avatar Loading" />
              </EnhancedAvatar>
              <EnhancedAvatar
                variant="glass"
                size="lg"
                state="error"
                className="h-12 w-12"
              >
                <img src="https://i.pravatar.cc/150?img=15" alt="Avatar Error" />
              </EnhancedAvatar>
              <EnhancedAvatar
                variant="glass"
                size="lg"
                state="success"
                className="h-12 w-12"
              >
                <img src="https://i.pravatar.cc/150?img=16" alt="Avatar Success" />
              </EnhancedAvatar>
              <EnhancedAvatar
                variant="glass"
                size="lg"
                state="offline"
                className="h-12 w-12"
              >
                <img src="https://i.pravatar.cc/150?img=17" alt="Avatar Offline" />
              </EnhancedAvatar>
              <EnhancedAvatar
                variant="glass"
                size="lg"
                state="online"
                className="h-12 w-12"
              >
                <img src="https://i.pravatar.cc/150?img=18" alt="Avatar Online" />
              </EnhancedAvatar>
            </div>
          </div>
        </div>
      </section>

      {/* Enhanced Badge Demo */}
      <section className="space-y-6">
        <h2 className="text-xl font-mono text-cyber-green">Enhanced Badge</h2>
        <div className="space-y-6">
          <div className="space-y-4">
            <label htmlFor="badge-variants" className="font-mono text-cyber-blue">
              Badge Variants
            </label>
            <div className="flex space-x-4">
              <EnhancedBadge variant="default">Default</EnhancedBadge>
              <EnhancedBadge variant="secondary">Secondary</EnhancedBadge>
              <EnhancedBadge variant="destructive">Destructive</EnhancedBadge>
              <EnhancedBadge variant="outline">Outline</EnhancedBadge>
              <EnhancedBadge variant="glass">Glass</EnhancedBadge>
              <EnhancedBadge variant="glass-dark">Glass Dark</EnhancedBadge>
              <EnhancedBadge variant="neon-glass">Neon Glass</EnhancedBadge>
              <EnhancedBadge variant="subtle">Subtle</EnhancedBadge>
              <EnhancedBadge variant="outline-glass">Outline Glass</EnhancedBadge>
              <EnhancedBadge variant="elevated">Elevated</EnhancedBadge>
              <EnhancedBadge variant="floating">Floating</EnhancedBadge>
            </div>
          </div>

          <div className="space-y-4">
            <label htmlFor="badge-sizes" className="font-mono text-cyber-blue">
              Badge Sizes
            </label>
            <div className="flex space-x-4">
              <EnhancedBadge variant="glass" size="xs">XS</EnhancedBadge>
              <EnhancedBadge variant="glass" size="sm">SM</EnhancedBadge>
              <EnhancedBadge variant="glass" size="default">Default</EnhancedBadge>
              <EnhancedBadge variant="glass" size="lg">LG</EnhancedBadge>
              <EnhancedBadge variant="glass" size="xl">XL</EnhancedBadge>
            </div>
          </div>

          <div className="space-y-4">
            <label htmlFor="badge-states" className="font-mono text-cyber-blue">
              Badge States
            </label>
            <div className="flex space-x-4">
              <EnhancedBadge variant="glass" state="default">Default</EnhancedBadge>
              <EnhancedBadge variant="glass" state="loading">Loading</EnhancedBadge>
              <EnhancedBadge variant="glass" state="error">Error</EnhancedBadge>
              <EnhancedBadge variant="glass" state="success">Success</EnhancedBadge>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}