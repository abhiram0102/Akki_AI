import React, { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import { motion } from "framer-motion";
import { useScrollAnimation } from "@/hooks/use-scroll-animation";

type NewItemForm = {
  name: string;
  description: string;
  category: string;
  subcategory: string;
  version: string;
  author: string;
  repository_url: string;
  documentation_url: string;
  install_command: string;
  config_schema: string;
  is_public: boolean;
  is_verified: boolean;
};

const Marketplace = () => {
  const [items, setItems] = useState<Array<any>>([]);
  const [categories, setCategories] = useState<Array<string>>([]);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedItem, setSelectedItem] = useState<any | null>(null);
  const [installedItems, setInstalledItems] = useState<Array<any>>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [installing, setInstalling] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<string>("browse"); // browse, installed, add
  const [newItemForm, setNewItemForm] = useState<NewItemForm>({
    name: "",
    description: "",
    category: "tool",
    subcategory: "",
    version: "1.0.0",
    author: "",
    repository_url: "",
    documentation_url: "",
    install_command: "",
    config_schema: "{}",
    is_public: false,
    is_verified: false,
  });

  const { toast } = useToast();

  useEffect(() => {
    fetchMarketplaceItems();
    fetchCategories();
    fetchInstalledItems();
  }, []); // Empty array deps for initial load

  // Variants for marketplace items
  const itemVariants = {
    initial: { scale: 0.95, opacity: 0, y: 10 },
    animate: { scale: 1, opacity: 1, y: 0, transition: { type: "spring", stiffness: 300, damping: 20 } },
  };

  const listVariants = {
    hidden: {},
    initial: {},
    animate: {
      transition: {
        staggerChildren: 0.05,
        delayChildren: 0.05,
      },
    },
  };

  const fetchMarketplaceItems = async () => {
    setLoading(true);
    try {
      let url = `/api/protected/marketplace/items`;
      const params = new URLSearchParams();

      if (selectedCategory) params.append("category", selectedCategory);
      if (searchQuery) params.append("q", searchQuery);
      if (params.toString()) url += `?${params.toString()}`;

      const response = await api.get(url);
      setItems(response);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      toast({
        title: "Failed to load marketplace items",
        description: message,
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const fetchCategories = async () => {
    try {
      // Get unique categories from items
      const response = await api.get(`/api/protected/marketplace/items`);
      const uniqueCategories: string[] = [...new Set((response as any[]).map((item: any) => String(item.category)))];
      setCategories(uniqueCategories);
    } catch (error: unknown) {
      console.error("Failed to fetch categories:", error);
    }
  };

  const fetchInstalledItems = async () => {
    try {
      const response = await api.get(`/api/protected/marketplace/installed`);
      setInstalledItems(response);
    } catch (error: unknown) {
      console.error("Failed to fetch installed items:", error);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    await fetchMarketplaceItems();
  };

  const handleInstall = async (itemId: string) => {
    setInstalling(true);
    try {
      await api.post(`/api/protected/marketplace/items/${itemId}/install`);
      await fetchInstalledItems();
      toast({
        title: "Item installed",
        description: "The item has been successfully installed",
      });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      toast({
        title: "Failed to install item",
        description: message,
        variant: "destructive",
      });
    } finally {
      setInstalling(false);
    }
  };

  const handleUninstall = async (itemId: string) => {
    try {
      await api.delete(`/api/protected/marketplace/items/${itemId}/install`);
      await fetchInstalledItems();
      toast({
        title: "Item uninstalled",
        description: "The item has been successfully uninstalled",
      });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      toast({
        title: "Failed to uninstall item",
        description: message,
        variant: "destructive",
      });
    }
  };

  const handleToggleEnabled = async (itemId: string, isEnabled: boolean) => {
    try {
      await api.put(`/api/protected/marketplace/items/${itemId}/toggle`, { is_enabled: isEnabled });
      await fetchInstalledItems();
      toast({
        title: isEnabled ? "Item enabled" : "Item disabled",
        description: `The item has been ${isEnabled ? "enabled" : "disabled"}`,
      });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      toast({
        title: "Failed to update item status",
        description: message,
        variant: "destructive",
      });
    }
  };

  const handleRateItem = async (itemId: string, rating: number) => {
    try {
      await api.post(`/api/protected/marketplace/items/${itemId}/rate`, { rating });
      await fetchMarketplaceItems();
      toast({
        title: "Item rated",
        description: "Your rating has been submitted",
      });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      toast({
        title: "Failed to rate item",
        description: message,
        variant: "destructive",
      });
    }
  };

  const handleAddItem = async () => {
    setLoading(true);
    try {
      // Parse config_schema from string to object
      let configSchemaObject: object;
      try {
        configSchemaObject = JSON.parse(newItemForm.config_schema);
      } catch (e) {
        configSchemaObject = {};
      }
      const formData = {
        ...newItemForm,
        config_schema: configSchemaObject
      };

      const response = await api.post(`/api/protected/marketplace/items`, formData);
      setNewItemForm({
        name: "",
        description: "",
        category: "tool",
        subcategory: "",
        version: "1.0.0",
        author: "",
        repository_url: "",
        documentation_url: "",
        install_command: "",
        config_schema: "{}",
        is_public: false,
        is_verified: false,
      });
      await fetchMarketplaceItems();
      toast({
        title: "Item added",
        description: "The item has been successfully added to the marketplace",
      });
      setActiveTab("browse"); // Switch back to browse tab
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      toast({
        title: "Failed to add item",
        description: message,
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleNewItemChange = (field: string, value: string | boolean) => {
    setNewItemForm((prev: NewItemForm) => ({
      ...prev,
      [field]: value
    }));
  };

  if (selectedItem) {
    return (
      <div className="flex-1 flex flex-col" style={{ background: 'rgba(0,0,0,0.2)' }}>
        <div className="flex items-center justify-between px-6 py-4 border-b" style={{ borderColor: 'rgba(255,255,255,0.05)', background: 'rgba(0,0,0,0.1)' }}>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSelectedItem(null)}
              className="p-2 text-gray-400 hover:text-white rounded-lg transition-colors"
            >
              <i className="fas fa-arrow-left text-xs" />
            </button>
            <div className="flex items-center gap-2">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-gradient-to-br from-indigo-500 to-blue-500">
                <i className="fas fa-box text-white text-sm" />
              </div>
              <div>
                <h1 className="font-display text-xl font-black text-white tracking-wider">
                  Item Details
                </h1>
                <p className="text-sm text-gray-400 font-mono">
                  View marketplace item details
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => handleInstall(selectedItem.id)}
              disabled={installing}
              className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-emerald-500 to-green-500 text-white font-bold text-sm rounded-lg disabled:opacity-50 hover:from-emerald-400 hover:to-green-400 transition-colors"
            >
              {installing ? "Installing..." : "Install Item"}
            </button>
          </div>
        </div>

        <div className="flex-1 p-6 overflow-y-auto">
          <div className="space-y-6">
            <div className="rounded-lg p-6" style={{ background: 'rgba(0,0,0,0.5)' }}>
              <h2 className="font-mono font-bold text-indigo-400 text-lg mb-4">
                {selectedItem.name}
              </h2>
              <p className="text-gray-400 mb-2">
                {selectedItem.description || "No description available"}
              </p>
              <div className="grid grid-cols-2 gap-4 text-sm text-gray-300">
                <div>
                  <span className="font-mono">Category:</span> {selectedItem.category}
                </div>
                <div>
                  <span className="font-mono">Subcategory:</span> {selectedItem.subcategory || "N/A"}
                </div>
                <div>
                  <span className="font-mono">Version:</span> {selectedItem.version}
                </div>
                <div>
                  <span className="font-mono">Author:</span> {selectedItem.author || "Unknown"}
                </div>
                <div>
                  <span className="font-mono">Rating:</span>
                  <div className="flex items-center gap-1">
                    {[1, 2, 3, 4, 5].map(star => (
                      <i
                        key={star}
                        className={`fas fa-star ${star <= selectedItem.rating ? "text-yellow-400" : "text-gray-500"}`}
                      />
                    ))}
                    <span className="text-gray-400 ml-1">({selectedItem.rating.toFixed(1)})</span>
                  </div>
                </div>
                <div>
                  <span className="font-mono">Downloads:</span> {selectedItem.download_count}
                </div>
                <div style={{ display:'flex',alignItems:'center',gap:6,marginTop:8 }}>
                  {[1,2,3,4,5].map(star => (
                    <button
                      key={star}
                      onClick={() => handleRateItem(selectedItem.id, star)}
                      style={{ background:'none',border:'none',cursor:'pointer',fontSize:18,color: star <= Math.round(selectedItem.rating || 0) ? '#fbbf24' : 'rgba(255,255,255,0.20)',padding:2 }}
                    >
                      <i className={`fas fa-star`} />
                    </button>
                  ))}
                  <span style={{ fontFamily:'monospace',fontSize:10,color:'rgba(255,255,255,0.40)' }}>
                    ({(selectedItem.rating || 0).toFixed(1)})
                  </span>
                </div>
                <div>
                  <span className="font-mono">Public:</span>
                  <span
                  className={`px-2 py-1 rounded-full text-xs ${selectedItem.is_public ? "text-green-400" : "text-red-400"}`}
                  style={{ background: selectedItem.is_public ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)' }}>
                    {selectedItem.is_public ? "Yes" : "No"}
                  </span>
                </div>
                <div>
                  <span className="font-mono">Verified:</span>
                  <span
                  className={`px-2 py-1 rounded-full text-xs ${selectedItem.is_verified ? "text-blue-400" : "text-gray-400"}`}
                  style={{ background: selectedItem.is_verified ? 'rgba(59,130,246,0.2)' : 'rgba(107,114,128,0.2)' }}>
                    {selectedItem.is_verified ? "Yes" : "No"}
                  </span>
                </div>
              </div>
            </div>

            {selectedItem.repository_url || selectedItem.documentation_url || selectedItem.install_command && (
              <div className="rounded-lg p-6" style={{ background: 'rgba(0,0,0,0.5)' }}>
                <h2 className="font-mono font-bold text-indigo-400 text-lg mb-4">
                  More Information
                </h2>
                <div className="space-y-4">
                  {selectedItem.repository_url && (
                    <div>
                      <h3 className="font-mono font-bold text-white mb-2">Repository</h3>
                      <a
                        href={selectedItem.repository_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-indigo-300 hover:text-indigo-200 underline"
                      >
                        {selectedItem.repository_url}
                      </a>
                    </div>
                  )}
                  {selectedItem.documentation_url && (
                    <div>
                      <h3 className="font-mono font-bold text-white mb-2">Documentation</h3>
                      <a
                        href={selectedItem.documentation_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-indigo-300 hover:text-indigo-200 underline"
                      >
                        {selectedItem.documentation_url}
                      </a>
                    </div>
                  )}
                  {selectedItem.install_command && (
                    <div>
                      <h3 className="font-mono font-bold text-white mb-2">Install Command</h3>
                      <div className="rounded-lg p-4 font-mono" style={{ background: 'rgba(0,0,0,0.3)' }}>
                        {selectedItem.install_command}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {selectedItem.config_schema && Object.keys(selectedItem.config_schema).length > 0 && (
              <div className="rounded-lg p-6" style={{ background: 'rgba(0,0,0,0.5)' }}>
                <h2 className="font-mono font-bold text-indigo-400 text-lg mb-4">
                  Configuration Schema
                </h2>
                <div className="rounded-lg p-4" style={{ background: 'rgba(0,0,0,0.3)' }}>
                  <pre className="text-xs text-gray-300">{JSON.stringify(selectedItem.config_schema, null, 2)}</pre>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col cursor-custom" style={{ background: 'rgba(0,0,0,0.2)' }}>
      <div className="flex items-center justify-between px-6 py-4 border-b" style={{ borderColor: 'rgba(255,255,255,0.05)', background: 'rgba(0,0,0,0.1)' }}>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-gradient-to-br from-indigo-500 to-blue-500">
            <i className="fas fa-box text-white text-sm" />
          </div>
          <div>
            <h1 className="font-display text-xl font-black text-white tracking-wider">
              Integration Marketplace
            </h1>
            <p className="text-sm text-gray-400 font-mono">
              Browse, install, and manage tools, agents, and data sources
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setActiveTab("add")}
            className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-indigo-500 to-blue-500 text-white font-bold text-sm rounded-lg hover:from-indigo-400 hover:to-blue-400 transition-all duration-300 hover:scale-[1.02] hover:-translate-y-1"
          >
            + Add Item
          </button>
        </div>
      </div>

      <div className="flex-1 p-6">
        <div className="flex items-center gap-4 mb-6">
          <div className="flex-1">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search marketplace items..."
              className="w-full px-3 py-2 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-indigo-400 hover:border-indigo-300 transition-all duration-300"
              style={{ background: 'rgba(0,0,0,0.5)', borderColor: 'rgba(255,255,255,0.1)' }}
            />
          </div>

          <div className="relative">
            <button
              onClick={() => {
                setSelectedCategory(null);
                setSearchQuery("");
                fetchMarketplaceItems();
              }}
              className="p-2 text-gray-400 hover:text-white rounded-lg transition-all duration-300 hover:scale-[1.05]"
            >
              <i className="fas fa-filter text-xs transition-transform duration-300 hover:rotate-12" />
            </button>
          </div>
        </div>

        <div className="space-y-6">
          {activeTab === "browse" && (
            <motion.div
              initial={{ opacity: 0, y: 20, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -20, scale: 0.95 }}
              transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
              className="tab-content"
            >
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
                {categories.map((category) => (
                  <div
                    key={category}
                    onClick={async () => {
                      const newCat = category === selectedCategory ? null : category;
                      setSelectedCategory(newCat);
                      const url = newCat
                        ? `/api/protected/marketplace/items?category=${newCat}`
                        : `/api/protected/marketplace/items`;
                      try {
                        const response = await api.get(url);
                        setItems(response);
                      } catch(error) {
                        const message = error instanceof Error ? error.message : String(error);
                        toast({ title: "Failed to load marketplace items", description: message, variant: "destructive" });
                      }
                    }}
                    className={`w-full cursor-pointer p-4 rounded-lg transition-all duration-300 ${selectedCategory === category ? "border-2 border-indigo-400" : ""} hover:-translate-y-1 hover:scale-[1.02] hover:shadow-[0_0_15px_rgba(0,191,255,0.3)]`}
                    style={{ background: 'rgba(0,0,0,0.5)' }}
                  >
                    <div className="flex items-center space-x-3">
                      <div className="w-8 h-8 flex-shrink-0">
                        <div className="flex h-full w-full items-center justify-center rounded-md" style={{ background: 'rgba(99,102,241,0.2)' }}>
                          <i className="fas fa-box text-indigo-400"></i>
                        </div>
                      </div>
                      <div>
                        <h3 className="font-mono font-bold text-indigo-400">{category}</h3>
                        <p className="text-xs text-gray-400 mt-1">
                          {items.filter(item => item.category === category).length} items
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="rounded-lg p-6" style={{ background: 'rgba(0,0,0,0.5)' }}>
                <h2 className="font-mono font-bold text-indigo-400 text-lg mb-4">
                  {selectedCategory ? `${selectedCategory} Items` : "All Marketplace Items"}
                </h2>

                {loading ? (
                  <div className="flex flex-col items-center justify-center text-center py-8">
                    <div className="animate-spin rounded-full border-2 w-8 h-8 mx-auto mb-2" style={{ borderColor: 'rgba(129,140,248,0.5)' }}></div>
                    <p className="text-gray-400">Loading items...</p>
                  </div>
                ) : items.length === 0 ? (
                  <div className="flex flex-col items-center justify-center text-center py-8">
                    <div className="text-indigo-400">
                      <i className="fas fa-box-open w-12 h-12 mx-auto mb-4"></i>
                    </div>
                    <p className="text-gray-400">
                      No items found. Try adjusting your filters or adding new items.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {items.map((item) => (
                      <div
                        key={item.id}
                        className="rounded-lg p-5 border transition-all duration-300 cursor-pointer hover:-translate-y-1 hover:scale-[1.02] hover:shadow-[0_0_15px_rgba(0,191,255,0.3)]"
                        style={{ background: 'rgba(0,0,0,0.6)', borderColor: 'rgba(255,255,255,0.05)' }}
                        onClick={() => setSelectedItem(item)}
                      >
                        <div className="space-y-4">
                          <div className="flex justify-between items-start">
                            <div>
                              <h3 className="font-mono font-bold text-white">{item.name}</h3>
                              <div className="flex items-center space-x-2 mt-1">
                                <span className="text-xs text-gray-400">
                                  {item.category}
                                  {item.subcategory ? ` (${item.subcategory})` : ""}
                                </span>
                              </div>
                            </div>
                            <div className="space-x-3 text-xs">
                              <div className="flex items-center">
                                <span className="font-mono">Downloads:</span>
                                <span className="text-gray-300">{item.download_count}</span>
                              </div>
                              <div className="flex items-center">
                                <span className="font-mono">Public:</span>
                                <span
                                  className={`px-2 py-0.5 rounded text-xs ${item.is_public ? "text-green-400" : "text-red-400"}`}
                                  style={{ background: item.is_public ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)' }}>
                                  {item.is_public ? "Yes" : "No"}
                                </span>
                              </div>
                              <div className="flex items-center">
                                <span className="font-mono">Verified:</span>
                                <span
                                  className={`px-2 py-0.5 rounded text-xs ${item.is_verified ? "text-blue-400" : "text-gray-400"}`}
                                  style={{ background: item.is_verified ? 'rgba(59,130,246,0.2)' : 'rgba(107,114,128,0.2)' }}>
                                  {item.is_verified ? "Yes" : "No"}
                                </span>
                              </div>
                            </div>
                          </div>
                          <p className="text-gray-400 line-clamp-2">
                            {item.description || "No description available"}
                          </p>
                          <div className="mt-3 pt-2 border-t" style={{ borderColor: 'rgba(0,0,0,0.1)' }}>
                            <div className="flex items-center space-x-2 text-xs text-gray-400">
                              <i className="fas fa-calendar-check"></i>
                              <span>Updated: {item.updated_at ? new Date(item.updated_at).toLocaleDateString() : "Recent"}</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </motion.div>
          )}

          {activeTab === "installed" && (
            <motion.div
              initial={{ opacity: 0, y: 20, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -20, scale: 0.95 }}
              transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
              className="tab-content"
            >
                <h2 className="font-mono font-bold text-indigo-400 text-lg mb-4">
                  Installed Items
                </h2>

              {installedItems.length === 0 ? (
                <p className="text-gray-400 text-center py-8">
                  No items installed yet. Browse the marketplace to install items.
                </p>
              ) : (
                <div className="space-y-4">
                  {installedItems.map((item) => {
                    const isEnabled = item.isEnabled ?? item.is_enabled ?? false;
                    return (
                    <div
                      key={item.id}
                      className="rounded-lg p-5 border transition-all duration-300 hover:-translate-y-1 hover:scale-[1.02] hover:shadow-[0_0_15px_rgba(0,191,255,0.3)]"
                      style={{ background: 'rgba(0,0,0,0.6)', borderColor: 'rgba(255,255,255,0.05)' }}
                    >
                      <div className="space-y-3">
                        <div className="flex justify-between items-start">
                          <div>
                            <h3 className="font-mono font-bold text-white">{item.name}</h3>
                            <div className="flex items-center space-x-2 mt-1">
                              <span className="text-xs text-gray-400">
                                {item.category}
                                {item.subcategory ? ` (${item.subcategory})` : ""}
                              </span>
                            </div>
                          </div>
                          <div className="flex items-center space-x-2 text-xs">
                            <span className="font-mono">Status:</span>
                            <span
                              className={`px-2 py-0.5 rounded ${isEnabled ? "text-green-400" : "text-red-400"}`}
                              style={{ background: isEnabled ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)' }}>
                              {isEnabled ? "Enabled" : "Disabled"}
                            </span>
                          </div>
                        </div>
                        <p className="text-gray-400">
                          {item.description || "No description available"}
                        </p>
                        <div className="mt-2 flex items-center space-x-3 text-xs text-gray-400">
                          <div className="flex items-center">
                            <i className="fas fa-download"></i>
                            <span>Installed:</span>
                            <span className="ml-1">{new Date(item.installed_at).toLocaleDateString()}</span>
                          </div>
                          <div className="flex items-center">
                            <i className="fas fa-shield-alt"></i>
                            <span>Status:</span>
                            <span className="ml-1">{isEnabled ? "Active" : "Inactive"}</span>
                          </div>
                        </div>
                        <div className="mt-2 flex justify-end">
                          <button
                            onClick={() => handleToggleEnabled(item.marketplace_item_id, !isEnabled)}
                            className={`flex items-center space-x-1 px-2 py-0.5 text-xs ${isEnabled ? "text-green-400" : "text-red-400"} rounded transition-colors`}
                            style={{ background: isEnabled ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)' }}
                          >
                            {isEnabled ? "Disable" : "Enable"}
                            <i className="fas fa-power-off ml-1"></i>
                          </button>
                          <button
                            onClick={() => handleUninstall(item.marketplace_item_id)}
                            className="ml-2 flex items-center space-x-1 px-2 py-0.5 text-xs text-red-400 rounded hover:text-white transition-colors" style={{ background: 'rgba(239,68,68,0.1)' }}
                          >
                            <i className="fas fa-trash"></i>
                            Remove
                          </button>
                        </div>
                      </div>
                  </div>
                  );
                  })}
                </div>
              )}
            </motion.div>
          )}

          {activeTab === "add" && (
            <motion.div
              initial={{ opacity: 0, y: 20, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -20, scale: 0.95 }}
              transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
              className="tab-content"
            >
              <div className="flex-1 flex flex-col" style={{ background: 'rgba(0,0,0,0.2)' }}>
                <div className="flex items-center justify-between px-6 py-4 border-b" style={{ borderColor: 'rgba(255,255,255,0.05)', background: 'rgba(0,0,0,0.1)' }}>
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => setActiveTab("browse")}
                      className="p-2 text-gray-400 hover:text-white rounded-lg transition-all duration-300 hover:scale-[1.05]"
                    >
                      <i className="fas fa-arrow-left text-xs transition-transform duration-300" />
                    </button>
                    <div className="flex items-center gap-2">
                      <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-gradient-to-br from-indigo-500 to-blue-500">
                        <i className="fas fa-plus text-white text-sm transition-transform duration-300 hover:scale-[1.1]" />
                      </div>
                      <div>
                        <h1 className="font-display text-xl font-black text-white tracking-wider">
                          Add Marketplace Item
                        </h1>
                        <p className="text-sm text-gray-400 font-mono">
                          Add a new tool, agent, or data source to the marketplace
                        </p>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="flex-1 p-6 overflow-y-auto">
                  <div className="rounded-lg p-6 border transition-all duration-300" style={{ background: 'rgba(0,0,0,0.5)', borderColor: 'rgba(255,255,255,0.1)' }}>
                    <form onSubmit={(e) => {
                      e.preventDefault();
                      handleAddItem();
                    }} className="space-y-6">
                    <div className="space-y-4">
                      <label className="block text-xs font-mono text-gray-400 mb-1">
                        Name
                      </label>
                      <div className="relative">
                        <input
                          type="text"
                          value={newItemForm.name}
                          onChange={(e) => handleNewItemChange("name", e.target.value)}
                          placeholder="Enter item name"
                          className="w-full px-4 py-3 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-indigo-400 hover:border-indigo-300 transition-all duration-300"
                          style={{ background: 'rgba(0,0,0,0.5)', borderColor: 'rgba(255,255,255,0.1)' }}
                        >
                        </input>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <label className="block text-xs font-mono text-gray-400 mb-1">
                        Description
                      </label>
                      <div className="relative">
                        <textarea
                          value={newItemForm.description}
                          onChange={(e) => handleNewItemChange("description", e.target.value)}
                          rows={4}
                          placeholder="Enter item description"
                          className="w-full px-4 py-3 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-indigo-400 hover:border-indigo-300 transition-all duration-300"
                          style={{ background: 'rgba(0,0,0,0.5)', borderColor: 'rgba(255,255,255,0.1)' }}
                        >
                        </textarea>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <label className="block text-xs font-mono text-gray-400 mb-1">
                        Category
                      </label>
                      <div className="relative">
                        <select
                          value={newItemForm.category}
                          onChange={(e) => handleNewItemChange("category", e.target.value)}
                          className="w-full px-4 py-3 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-indigo-400 hover:border-indigo-300 transition-all duration-300"
                          style={{ background: 'rgba(0,0,0,0.5)', borderColor: 'rgba(255,255,255,0.1)' }}
                        >
                          <option value="tool">Tool</option>
                          <option value="agent">Agent</option>
                          <option value="data_source">Data Source</option>
                        </select>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <label className="block text-xs font-mono text-gray-400 mb-1">
                        Subcategory (optional)
                      </label>
                      <div className="relative">
                        <input
                          type="text"
                          value={newItemForm.subcategory}
                          onChange={(e) => handleNewItemChange("subcategory", e.target.value)}
                          placeholder="Enter subcategory (e.g., nmap, metasploit for tools)"
                          className="w-full px-4 py-3 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-indigo-400 hover:border-indigo-300 transition-all duration-300"
                          style={{ background: 'rgba(0,0,0,0.5)', borderColor: 'rgba(255,255,255,0.1)' }}
                        >
                        </input>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <label className="block text-xs font-mono text-gray-400 mb-1">
                        Version
                      </label>
                      <div className="relative">
                        <input
                          type="text"
                          value={newItemForm.version}
                          onChange={(e) => handleNewItemChange("version", e.target.value)}
                          placeholder="Enter version (e.g., 1.0.0)"
                          className="w-full px-4 py-3 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-indigo-400 hover:border-indigo-300 transition-all duration-300"
                          style={{ background: 'rgba(0,0,0,0.5)', borderColor: 'rgba(255,255,255,0.1)' }}
                        >
                        </input>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <label className="block text-xs font-mono text-gray-400 mb-1">
                        Author (optional)
                      </label>
                      <div className="relative">
                        <input
                          type="text"
                          value={newItemForm.author}
                          onChange={(e) => handleNewItemChange("author", e.target.value)}
                          placeholder="Enter author name"
                          className="w-full px-4 py-3 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-indigo-400 hover:border-indigo-300 transition-all duration-300"
                          style={{ background: 'rgba(0,0,0,0.5)', borderColor: 'rgba(255,255,255,0.1)' }}
                        >
                        </input>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <label className="block text-xs font-mono text-gray-400 mb-1">
                        Repository URL (optional)
                      </label>
                      <div className="relative">
                        <input
                          type="text"
                          value={newItemForm.repository_url}
                          onChange={(e) => handleNewItemChange("repository_url", e.target.value)}
                          placeholder="Enter repository URL"
                          className="w-full px-4 py-3 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-indigo-400 hover:border-indigo-300 transition-all duration-300"
                          style={{ background: 'rgba(0,0,0,0.5)', borderColor: 'rgba(255,255,255,0.1)' }}
                        >
                        </input>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <label className="block text-xs font-mono text-gray-400 mb-1">
                        Documentation URL (optional)
                      </label>
                      <div className="relative">
                        <input
                          type="text"
                          value={newItemForm.documentation_url}
                          onChange={(e) => handleNewItemChange("documentation_url", e.target.value)}
                          placeholder="Enter documentation URL"
                          className="w-full px-4 py-3 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-indigo-400 hover:border-indigo-300 transition-all duration-300"
                          style={{ background: 'rgba(0,0,0,0.5)', borderColor: 'rgba(255,255,255,0.1)' }}
                        >
                        </input>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <label className="block text-xs font-mono text-gray-400 mb-1">
                        Install Command (optional)
                      </label>
                      <div className="relative">
                        <input
                          type="text"
                          value={newItemForm.install_command}
                          onChange={(e) => handleNewItemChange("install_command", e.target.value)}
                          placeholder="Enter install command"
                        className="w-full px-4 py-3 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-indigo-400 hover:border-indigo-300 transition-all duration-300"
                          style={{ background: 'rgba(0,0,0,0.5)', borderColor: 'rgba(255,255,255,0.1)' }}
                        >
                        </input>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <label className="block text-xs font-mono text-gray-400 mb-1">
                        Configuration Schema (JSON, optional)
                      </label>
                      <div className="relative">
                        <textarea
                          value={newItemForm.config_schema}
                          onChange={(e) => handleNewItemChange("config_schema", e.target.value)}
                          rows={4}
                          placeholder='Enter JSON schema for configuration (e.g., {"type":"object","properties":{"apiKey":{"type":"string"}}}'
                          className="w-full px-4 py-3 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-indigo-400 hover:border-indigo-300 transition-all duration-300"
                          style={{ background: 'rgba(0,0,0,0.5)', borderColor: 'rgba(255,255,255,0.1)' }}
                        >
                        </textarea>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <div className="flex items-center space-x-3">
                        <input
                          type="checkbox"
                          checked={newItemForm.is_public}
                          onChange={(e) => handleNewItemChange("is_public", e.target.checked)}
                          className="h-4 w-4 text-indigo-600 hover:text-indigo-400 transition-colors duration-200"
                        />
                        <label className="text-xs font-mono text-gray-300">
                          Public item (available to all users)
                        </label>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <div className="flex items-center space-x-3">
                        <input
                          type="checkbox"
                          checked={newItemForm.is_verified}
                          onChange={(e) => handleNewItemChange("is_verified", e.target.checked)}
                          className="h-4 w-4 text-indigo-600 hover:text-indigo-400 transition-colors duration-200"
                        />
                        <label className="text-xs font-mono text-gray-300">
                          Verified item
                        </label>
                      </div>
                    </div>

                    <div className="space-y-6">
                      <button
                        type="submit"
                        disabled={loading}
                        className="w-full flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-indigo-500 to-blue-500 text-white font-bold text-sm rounded-lg disabled:opacity-50 hover:from-indigo-400 hover:to-blue-400 transition-all duration-300 hover:scale-[1.02] hover:-translate-y-1"
                      >
                        {loading ? "Adding..." : "Add Item to Marketplace"}
                      </button>
                    </div>
                  </form>
                </div>
              </div>
              </div>
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Marketplace;