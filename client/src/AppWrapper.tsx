import { Switch, Route, useLocation } from "wouter";
import { motion } from "framer-motion";
import { routeVariants } from "@/motion";
import NotFound from "@/pages/not-found";
import Login from "@/pages/login";
import Dashboard from "@/pages/dashboard";
import Agents from "@/pages/agents";
import Workflows from "@/pages/workflows";
import ReportBuilder from "@/pages/report-builder";
import Marketplace from "@/pages/marketplace";

function AppWrapper() {
  const location = useLocation();

  return (
    <motion.location
      key={location.pathname}
      initial={false}
      animate
      exit
      variants={routeVariants}
    >
      <Switch>
        <Route path="/login" component={Login} />
        <Route path="/talk" component={Dashboard} />
        <Route path="/coding" component={Dashboard} />
        <Route path="/redteam" component={Dashboard} />
        <Route path="/osint" component={Dashboard} />
        <Route path="/reports" component={ReportBuilder} />
        <Route path="/tutor" component={Dashboard} />
        <Route path="/agents" component={Agents} />
        <Route path="/workflows" component={Workflows} />
        <Route path="/marketplace" component={Marketplace} />
        <Route path="/" component={Dashboard} />
        <Route component={NotFound} />
      </Switch>
    </motion.location>
  );
}

export default AppWrapper;