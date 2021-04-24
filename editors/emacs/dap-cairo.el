(require 'dap-mode)

(defcustom dap-cairo-debug-program '("cairo-dap")
  "The path to cairo-dap"
  :group 'dap-cairo
  :type '(repeat strig))

(defun dap-cairo--populate-start-file-args (conf)
  "Populate CONF with the required arguments."
  (let ((cwd (lsp-find-session-folder (lsp-session) (buffer-file-name))))
    (-> conf
      (dap--put-if-absent :type "cairo")
      (dap--put-if-absent :cwd cwd)
      (dap--put-if-absent :debugServer 9999)
      (dap--put-if-absent :port 9999)
      (dap--put-if-absent :hostName "localhost")
      (dap--put-if-absent :host "localhost"))))

(dap-register-debug-provider "cairo" 'dap-cairo--populate-start-file-args)

(dap-register-debug-template "Run Cairo"
			     (list :type "cairo"
				   :request "attach"
				   :cwd nil
				   :program nil
				   :name "Cairo::Run"))
