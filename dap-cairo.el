(require 'dap-mode)

(defcustom dap-cairo-debug-program '("cairo-dap")
  "The path to cairo-dap"
  :group 'dap-cairo
  :type '(repeat strig))

(defun dap-cairo--populate-start-file-args (conf)
  "Populate CONF with the required arguments."
  (let ((cwd (lsp-find-session-folder (lsp-session) (buffer-file-name))))
    (-> conf
      (dap--put-if-absent :dap-server-path dap-cairo-debug-program)
      (dap--put-if-absent :task-args (list "--layout=small"))
      (dap--put-if-absent :type "cairo_dap")
      (dap--put-if-absent :targe (read-file-name "Select file to debug."))
      (dap--put-if-absent :projectDir cwd)
      (dap--put-if-absent :cwd cwd))))

(dap-register-debug-provider "cairo" 'dap-cairo--populate-start-file-args)

(dap-register-debug-template "Run Cairo"
			     (list :type "cairo"
				   :request "launch"
				   :cwd nil
				   :program nil
				   :name "Cairo::Run"))
